# coding: UTF-8
import pickle
import os.path
import sys
import csv
import re
import configparser
# Python 3.12 で multiprocessing.pool の内部 API (_get_tasks 等) が削除されたため、
# istarmap (Pool.istarmap のモンキーパッチ) から concurrent.futures.ProcessPoolExecutor に移行。
# worker 関数はグローバル変数への依存をなくし、必要な引数をすべて明示的に受け取る設計に変更。
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
#
from docopt import docopt
from tqdm import tqdm
import json

_prog = os.path.basename(__file__)

__doc__ = f"""{_prog}

Usage:
    {_prog} all [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {_prog} create [<classFile>] [--with-activate] [--dry-run] [--debug]
    {_prog} enroll [<enrollFile>] [<coursesFile>] [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {_prog} unenroll <userId> <courses>... [--dry-run] [--debug]
    {_prog} remove <courses>... [--dry-run] [--debug]
    {_prog} lists <outputCsv> [--all-states] [--all-courses] [--debug]
    {_prog} info <courses>... [--detail] [--debug]
    {_prog} user <userId>
    {_prog} crawl <coursesFile> <outputCsv> [--debug]
    {_prog} get-stream <coursesFile> <keyword> <outputCsv>
    {_prog} archive <courses>... [--dry-run] [--debug]
    {_prog} active <courses>... [--dry-run] [--debug]
    {_prog} owner <owner> <courses>... [--dry-run] [--debug]
    {_prog} -h | --help

Options:
    all         create new courses and enroll users on the Google Classroom.
    create      create only new courses (default: classes.csv).
                --with-activate: activate when course created
    enroll      enroll users on courses (default: enrollments.csv).
                --teacher: invite / enroll Teacher role(default Student role)
                --foreign-domain: force invite mode
    unenroll    unenroll user from courses(course_id1, course_id2, ...).
    remove      remove courses from classroom(course_id1 course_id2 ... ).
    lists       lists of all active courses
                --all-states: include provision and archived courses
                --all-courses: include courses not matching name formats
    info        information of course information.
                --detail: include course enrolled / invited students information.
    user        information of user.
    crawl       display situations of students registration.
    get-stream  get courses stream(announcements) with [keyword]
    archive     change courses(course_id1, course_id2, ...) state to ARCHIVE.
    active      change courses(course_id1, course_id2, ...) state to ACTIVE.
    owner       change owner of courses(course_id1, course_i2, ...)
    -h --help   Show this screen and exit.
"""


def parse_options():
    """parse_options(void)
    """
    _options = {}
    args = docopt(__doc__)

    _options["classFile"] = args["<classFile>"] if args["<classFile>"] else "classes.csv"
    _options["enrollFile"] = args["<enrollFile>"] if args["<enrollFile>"] else "enrollments.csv"
    _options["courseIdFile"] = args["<coursesFile>"] if args["<coursesFile>"] else "coursesID.csv"
    if args["create"]:
        _exec_mode = "create"
        _options["courseActivate"] = bool(args["--with-activate"])
    elif args["enroll"]:
        _exec_mode = "enroll"
        _options["teacherRole"] = bool(args["--teacher"])
        _options["foreignDomain"] = bool(args["--foreign-domain"])
    elif args["unenroll"]:
        _exec_mode = "unenroll"
        _options["userId"] = args["<userId>"]
        _options["courses"] = args["<courses>"]
    elif args["remove"]:
        _exec_mode = "remove"
        _options["courses"] = args["<courses>"]
    elif args["lists"]:
        _exec_mode = "lists"
        _options["listAllStates"] = bool(args["--all-states"])
        _options["listAllCourses"] = bool(args["--all-courses"])
        _options["outputCsv"] = args["<outputCsv>"]
    elif args["info"]:
        _exec_mode = "info"
        _options["courses"] = args["<courses>"]
        _options["detail"] = bool(args["--detail"])
    elif args["user"]:
        _exec_mode = "user"
        _options["userId"] = args["<userId>"]
    elif args["crawl"]:
        _exec_mode = "crawl"
        _options["outputCsv"] = args["<outputCsv>"]
    elif args["get-stream"]:
        _exec_mode = "getStream"
        _options["keyword"] = args["<keyword>"]
        _options["outputCsv"] = args["<outputCsv>"]
    elif args["archive"]:
        _exec_mode = "archive"
        _options["courses"] = args["<courses>"]
    elif args["active"]:
        _exec_mode = "active"
        _options["courses"] = args["<courses>"]
    elif args["owner"]:
        _exec_mode = "owner"
        _options["owner"] = args["<owner>"]
        _options["courses"] = args["<courses>"]
    elif args["all"]:
        _exec_mode = "default"
    # print(_exec_mode)
    _options["dry-run"] = bool(args["--dry-run"])
    _options["debug"] = bool(args["--debug"])
    if _options["debug"]:
        print("  {0:<20}{1:<20}{2:<20}".format("key", "value", "type"))
        print("  {0:-<60}".format(""))
        for k, v in args.items():
            print("  {0:<20}{1:<20}{2:<20}".format(
                str(k), str(v), str(type(v))))

    return _exec_mode, _options


def api_init():
    """ Initialization of Classroom API for enroll teacher / student to each classroom
    """
    scopes = ["https://www.googleapis.com/auth/classroom.courses",
              "https://www.googleapis.com/auth/classroom.rosters",
              "https://www.googleapis.com/auth/classroom.profile.emails",
              "https://www.googleapis.com/auth/classroom.announcements.readonly"]
    # If modifying these scopes, delete the file token.pickle.
    # TODO: token.pickle は pickle ベースの旧形式。google-auth の新バージョンでは
    #       token.json (creds.to_json() / Credentials.from_authorized_user_info()) が推奨。
    #       Python バージョンアップ時にライブラリも更新する場合は合わせて移行すること。
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    _service_classroom = build("classroom", "v1", credentials=creds)
    return creds, _service_classroom


def read_data():
    """read_data(void)
    """
    # set filename configured by the execute option
    _class_file = options["classFile"] if "classFile" in options else "classes.csv"
    _enroll_file = options["enrollFile"] if "enrollFile" in options else "enrollments.csv"
    _course_id_file = options["courseIdFile"] if "courseIdFile" in options else "coursesID.csv"
    # read classes.csv for opened classroom
    # csv format:
    # class_code(Key), subjectName, teacher id, className
    if exec_mode == "create":
        with open(_class_file, "r") as _f:
            for line in _f:
                if line == "\n":
                    continue
                line = line.rstrip("\n").split(",")
                if line[0][0] == "#":
                    continue
                try:  # Check duplicated line in classFile
                    class_subjects[line[0]]
                    continue
                except KeyError:  # first appear line is active
                    class_subjects[line[0]] = line[1]
                    class_teachers[line[0]] = line[2]
                    class_sections[line[0]] = line[3]
    # read users.csv, getting email address from user id
    # csv format:
    # user id, user Email
    if exec_mode in ("enroll", "unenroll", "create"):
        with open("users.csv", "r") as _f:
            for line in _f:
                if line == "\n":
                    continue
                line = line.rstrip("\n").split(",")
                if line[0][0] == "#":
                    continue
                user_emails[line[0]] = line[1]
    # read enroll user lists for each class
    # csv format:
    # class_code(Multiple Key), user id
    # if any(x in options for x in ("enroll", "unenroll", "create")):
    if exec_mode in ("enroll", "unenroll", "create"):
        with open(_enroll_file, "r") as _f:
            for line in _f:
                if line == "\n":
                    continue
                line = line.rstrip("\n").split(",")
                if line[0][0] == "#":
                    continue
                # multiple values for single key
                enroll_users.setdefault(line[0], []).append(line[1])
    # read already created course ID
    # csv format:
    # class_code, Google Classroom course id
    if exec_mode != "create":
        with open(_course_id_file, "r") as _f:
            for line in _f:
                if line == "\n":
                    continue
                line = line.rstrip("\n").split(",")
                if line[0][0] == "#":
                    continue
                # classCode regex match?
                if re.match(class_code_regex, line[0]):
                    course_lists[line[0]] = line[1]
                    course_names[line[0]] = line[2]
                    course_owners[line[0]] = line[3]
                    class_codes[line[1]] = line[0]  # reverse index
                    if len(line) >= 6:
                        # overwrite by courseIdFile
                        class_sections[line[0]] = line[5]
                        class_teachers[line[0]] = line[6]
                    else:
                        class_sections[line[0]] = None
                        class_teachers[line[0]] = None
    if options["debug"]:
        print(course_lists)
    return _course_id_file


def create_classroom(_class_subject, _class_section, _class_teacher):
    """ create_classroom(_class_subject, _class_section, _class_teacher)
    """
    _course_state = "ACTIVE" if options["courseActivate"] else "PROVISIONED"
    try:
        course = {
            "name": _class_subject,
            "ownerId": _class_teacher,
            "section": _class_section,
            "courseState": _course_state
        }
        course = service_classroom.courses().create(body=course).execute()
        _course_id = course.get("id")
        print("Course created: {0} ({1})".format(
            course.get("name"), _course_id))
        _enroll_code = course.get("enrollmentCode")
    except HttpError as _e:
        error = json.loads(_e.content).get("error")
        if error.get("code") == 403:  # 403 is Permission Denied
            print("Permission Denied")
            _course_id = 0
            _enroll_code = ""
        else:
            raise
    return _course_id, _enroll_code


def add_admin_user(_course_id):
    """add_admin_user(_course_id)
    """
    _course_id = get_course_id(_course_id)
    # この関数はメインプロセスから直接呼ばれるため、グローバルの service 辞書を使用する。
    # worker 関数（invite_users_proc 等）はサブプロセスで実行されるためローカル _service を使うが、
    # add_admin_user / delete_admin_user はその対象外。
    if _course_id not in service:
        service[_course_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    teacher = {"userId": "me"}
    try:
        teacher = (
            service[_course_id].courses()
            .teachers()
            .create(courseId=_course_id, body=teacher)
            .execute()
        )
        if options["debug"]:
            print("Course {0} add Admin User".format(_course_id))
    except HttpError as _e:
        error = json.loads(_e.content).get("error")
        if error.get("code") == 409:  # 409 is already exists
            if options["debug"]:
                print("Already added Admin User")
        elif error.get("code") == 500:  # internal error
            print("Internal error encountered")
        else:
            raise


def delete_admin_user(_course_id):
    """delete_admin_user(_course_id)
    """
    _course_id = get_course_id(_course_id)
    if _course_id not in service:
        service[_course_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    try:
        service[_course_id].courses().teachers().delete(
            courseId=_course_id, userId="me"
        ).execute()
        if options["debug"]:
            print("Course {0} delete Admin User".format(_course_id))
    except HttpError as _e:
        error = json.loads(_e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            if options["debug"]:
                print(
                    "Course Admin Teacher {0} is not found".format(_course_id))
        else:
            raise


def delete_user(_course_ids, _user_id):
    """delete_user(_course_id, _user_id)
    """
    if '@' not in _user_id:
        _user_id = user_emails[_user_id]
    for _course_id in _course_ids:
        _course_id = get_course_id(_course_id)
        if options["dry-run"]:
            print("user {0} remove from course {1}".format(
                _user_id, _course_id))
        else:
            try:
                print('unenroll {0} from course id {1}'.format(
                    _user_id, _course_id))
                service_classroom.courses().students().delete(
                    courseId=_course_id, userId=_user_id).execute()
                print("success removed from student roll")
            except HttpError as _e:
                error = json.loads(_e.content).get("error")
                if error.get("code") == 404:  # 404 is NOT_FOUND
                    # if options["debug"]:
                    print("{0} is not found as student roll in course {1}".format(
                        _user_id, _course_id))
                    try:
                        service_classroom.courses().teachers().delete(
                            courseId=_course_id, userId=_user_id).execute()
                        print("success removed from teacher roll")
                    except HttpError as _e:
                        error = json.loads(_e.content).get("error")
                        if error.get("code") == 404:  # 404 is NOT_FOUND
                            print("{0} is not found as teacher roll in course {1}".format(
                                _user_id, _course_id))
                else:
                    raise


def update_courses(_course_ids, _owner=None):
    """update_courses(_course_ids)
    """
    _course_state = "ARCHIVED" if exec_mode == "archive" else "ACTIVE"
    for _course_id in _course_ids:
        _course_id = get_course_id(_course_id)
        _course_info = service_classroom.courses().get(id=_course_id).execute()
        _course_owner = _owner if _owner is not None else _course_info.get(
            "ownerId")
        body = {
            "id": _course_id,
            "courseState": _course_state,
            "name": _course_info.get("name"),
            "section": _course_info.get("section"),
            "description": _course_info.get("description"),
            "room": _course_info.get("room"),
            "ownerId": _course_owner
        }
        if options["dry-run"]:
            print("course {0} is changed {1}({2})".format(
                _course_id, _course_state, _course_owner))
        else:
            try:
                print('trying change state to {0} for course {1}({2})...'.format(
                    _course_state, _course_id, _course_owner))
                service_classroom.courses().update(
                    id=_course_id, body=body).execute()
                print('done')
            except HttpError as _e:
                error = json.loads(_e.content).get("error")
                if error.get("code") == 404:  # 404 is NOT_FOUND
                    if options["debug"]:
                        print(
                            "course {} is not found".format(_course_id))
                else:
                    raise


def invite_users(class_id):
    """invite_users(class_id)
    """
    _role = 'TEACHER' if options["teacherRole"] else 'STUDENT'
    users = []
    for user_id in enroll_users[class_id]:
        # Possibly not work properly(2021.04 add sira)
        _course_id = get_course_id(class_id)
        _invite_user = user_emails[user_id]
        user = {
            "courseId": _course_id,
            "userId": _invite_user,
            "role": _role
        }
        users.append(user)
        if options["debug"]:
            print([_course_id, user])
    results = []
    worker = partial(invite_users_proc, options=options, creds_classroom=creds_classroom)
    with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
        for result in tqdm(executor.map(worker, users), total=len(users)):
            results.append(result)
    for result in results:
        print(result)


def invite_users_proc(user, options, creds_classroom):
    """invite_users_proc(user, options, creds_classroom)
    """
    user_id = user.get("userId")
    _course_id = user.get("courseId")
    if options["debug"]:
        print([_course_id, user_id])
    if not options["dry-run"]:
        _service = build("classroom", "v1", credentials=creds_classroom)
        result = 'user={}'.format(user_id)
        try:
            user = _service.invitations().create(body=user).execute()
            result += " invite to {}.".format(_course_id)
        except HttpError as _e:
            error = json.loads(_e.content).get("error")
            if error.get("code") == 409:
                result += " is already invited to ({}).".format(_course_id)
            elif error.get("code") == 400:
                result += " is already member of ({}).".format(_course_id)
            elif error.get("code") == 401:
                print("Authentication error")
            elif error.get("code") == 403:
                print("Permission Denied in {}".format(_course_id))
            elif error.get("code") == 404:
                print("course {0} is not found".format(_course_id))
            else:
                raise
        return result


def create_users(class_id):
    """create_users(class_id)
    """
    course_ids = []
    users = []
    for user_id in enroll_users[class_id]:
        # Possibly not work properly(2021.04 add sira)
        _course_id = get_course_id(class_id)
        _enroll_user = user_emails[user_id]
        print('course_id={}, class_id={}, enrollUser={}'.format(
            _course_id, class_id, _enroll_user))
        user = {
            "userId": _enroll_user,
        }
        course_ids.append(_course_id)
        users.append(user)
        if options["debug"]:
            print([_course_id, user])
    if not options["dry-run"]:
        worker = partial(create_users_proc, options=options, creds_classroom=creds_classroom)
        with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
            for _ in tqdm(executor.map(worker, course_ids, users),
                          total=len(course_ids)):
                pass


def create_users_proc(_course_id, user, options, creds_classroom):
    """create_users_proc(_course_id, user, options, creds_classroom)
    """
    _service = build("classroom", "v1", credentials=creds_classroom)
    try:
        if options["teacherRole"]:
            user = (
                _service.courses()
                .teachers()
                .create(
                    courseId=_course_id,
                    body=user,
                )
                .execute()
            )
        else:
            user = (
                _service.courses()
                .students()
                .create(
                    courseId=_course_id,
                    body=user,
                )
                .execute()
            )
        print(
            'User {0} was enrolled as a user in the course with ID "{1}"'.format(
                user.get("profile").get("name").get("fullName"), _course_id
            )
        )
    except HttpError as _e:
        error = json.loads(_e.content).get("error")
        if error.get("code") == 409:
            print(
                "User {0} is already a member of this course.".format(
                    user.get("userId")
                )
            )
        elif error.get("code") == 403:
            print("...Permission Denied.")
        elif error.get("code") == 404:
            print("course {0} is not found".format(_course_id))
        else:
            print(error.get("code"))
            raise


def delete_classroom(_course_id):
    """delete_classroom(_course_id)
    """
    try:
        service_classroom.courses().delete(id=_course_id).execute()
        print("Course {0} has been removed".format(_course_id))
    except HttpError as _e:
        error = json.loads(_e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            print("Course ID {0} has already been deleted".format(_course_id))
        else:
            raise


def list_classroom():
    """list_classroom()
    """
    page_token = None
    courses = []
    if options["listAllStates"]:
        course_states = None
    else:
        course_states = "ACTIVE"
    while True:
        results = service_classroom.courses().list(pageSize=0, pageToken=page_token,
                                                   courseStates=course_states).execute()
        # if set pageSize=0, 500 responses are max queue( at 2020.05.06 )
        page_token = results.get('nextPageToken', None)
        # if _course['id'] != "105250506097979753968":
        courses += results.get("courses", [])
        if not page_token:
            break
    if not courses:
        print("No courses found")
    else:
        _total_courses = len(courses)
        print("total Courses: {} ".format(_total_courses))
        with open(options["outputCsv"], "w") as _f:
            writer = csv.writer(_f, lineterminator="\n")
            # csv indexes
            writer.writerow(
                [
                    "class_code",
                    "courseId",
                    "courseName",
                    "emailAddress",
                    "ownerId",
                    "courseSection",
                    "teacherNames",
                    "enrollCode",
                    "status",
                ]
            )
            # initialize CSV results
            results = []
            worker = partial(list_classroom_proc,
                             options=options,
                             creds_classroom=creds_classroom,
                             class_code_regex=class_code_regex)
            with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
                for result in tqdm(
                        executor.map(worker, courses), total=_total_courses):
                    if result:
                        results.append(result)
            # write csv file.
            writer.writerows(results)


def list_classroom_proc(course, options, creds_classroom, class_code_regex):
    """list_classroom_proc(course, options, creds_classroom, class_code_regex)
    """
    _course_id = course.get("id")   # notice changed..
    _service = build("classroom", "v1", credentials=creds_classroom)
    results = _service.courses().teachers().list(
        courseId=_course_id).execute()
    # '.*?([0-9]{5}[A-Z][0-9]{4})'
    _class_code = re.match(class_code_regex, course.get("name"))
    _owner_id = course.get("ownerId")
    try:
        _teacher_info = _service.userProfiles().get(
            userId=_owner_id).execute()
    except HttpError as _e:
        error = json.loads(_e.content).get("error")
        if error.get("code") == 403:  # 403 is unauthorized
            print("Not Authorized")
        elif error.get("code") == 500:  # internal error
            print("Internal error encountered")
        else:
            raise
        return False
    teachers = results.get("teachers", [])
    _teacher_names = ""
    for teacher in teachers:
        _teacher_names += "/" + str(teacher["profile"]["name"]["fullName"])
    if _class_code:
        return [
            _class_code.group(1),
            course.get("id"),
            course.get("name"),
            _teacher_info.get("emailAddress"),
            course.get("ownerId"),
            course.get("section"),
            _teacher_names.lstrip("/"),
            course.get("enrollmentCode"),
            course.get("courseState"),
        ]
    elif options["listAllCourses"]:
        return [
            None,
            course.get("id"),
            course.get("name"),
            _teacher_info.get("emailAddress"),
            course.get("ownerId"),
            course.get("section"),
            _teacher_names.lstrip("/"),
            course.get("enrollmentCode"),
            course.get("courseState"),
        ]
    else:
        return False


def info_classroom(_course_ids):
    """info_classroom(_course_ids)
    """
    for _course_id in _course_ids:
        _course_id = get_course_id(_course_id)
        _course_info = service_classroom.courses().get(id=_course_id).execute()
        print("course_id: {}".format(_course_info.get("id")))
        print("name    : {}".format(_course_info.get("name")))
        print("section : {}".format(_course_info.get("section")))
        print("status  : {}".format(_course_info.get("courseState")))
        _owner_id = _course_info.get("ownerId")
        print("ownerId  : {}".format(_owner_id))
        _teacher_info = service_classroom.userProfiles().get(userId=_owner_id).execute()
        print("owner : {}({})".format(_teacher_info.get(
            "emailAddress"), _teacher_info.get("name").get("fullName")))
        results = service_classroom.courses().teachers().list(
            courseId=_course_id).execute()
        teachers = results.get("teachers", [])
        _teacher_names = ""
        for teacher in teachers:
            _teacher_names += "/" + str(teacher["profile"]["name"]["fullName"])
        print("teacher : {}".format(_teacher_names))
        if options["detail"]:
            if _owner_id != admin_id:
                add_admin_user(_course_id)
            print("Enrolled user lists...")
            results = enrolled_students(_course_id)
            if results:
                for result in sorted(results):
                    print("{},{}".format(result[0], result[1]))
            print("Inviting user lists...")
            results = invited_students(_course_id)
            if results:
                for result in sorted(results):
                    print("{},{}".format(result[0], result[1]))
            if _owner_id != admin_id:
                delete_admin_user(_course_id)


def info_user(_user_id):
    """info_user(_user_id)
    """
    _user_info = service_classroom.userProfiles().get(userId=_user_id).execute()
    print("user_id  : {}".format(_user_info.get("id")))
    print("name     : {}".format(_user_info.get("name").get("fullName")))
    print("email    : {}".format(_user_info.get("emailAddress")))
    print("perm.    : ", end="")
    for _permission in _user_info.get("permissions"):
        print(_permission.get("permission"), " ", end="")
    print("")


def enrolled_students(_course_id):
    """enrolled_students(_course_id)
    """
    page_token = None
    user_ids = []
    while True:
        _course_students = service_classroom.courses().students().list(
            pageSize=0, courseId=_course_id, pageToken=page_token).execute()
        if "students" in _course_students:
            for course_student in _course_students.get("students"):
                user_ids.append(course_student.get("profile").get("id"))
            page_token = _course_students.get('nextPageToken', None)
            if not page_token:
                break
        else:
            break
    results = []
    if user_ids:
        worker = partial(info_classroom_proc, creds_classroom=creds_classroom)
        with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
            for result in tqdm(
                    executor.map(worker, user_ids), total=len(user_ids)):
                results.append(result)
    return results


def invited_students(_course_id):
    """invited_students(_course_id)
    """
    page_token = None
    user_ids = []
    while True:
        _invite_students = service_classroom.invitations().list(
            courseId=_course_id, pageSize=0, pageToken=page_token).execute()
        if "invitations" in _invite_students:
            for _invite_student in _invite_students.get("invitations"):
                user_ids.append(_invite_student.get("userId"))
            page_token = _invite_students.get('nextPageToken', None)
            if not page_token:
                break
        else:
            break
    results = []
    if user_ids:
        worker = partial(info_classroom_proc, creds_classroom=creds_classroom)
        with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
            for result in tqdm(
                    executor.map(worker, user_ids), total=len(user_ids)):
                results.append(result)
    return results


def info_classroom_proc(user_id, creds_classroom):
    """info_classroom_proc(user_id, creds_classroom)
    """
    _service = build("classroom", "v1", credentials=creds_classroom)
    results = _service.userProfiles().get(userId=user_id).execute()
    name = results.get("name").get("fullName")
    student_id = results.get("emailAddress")[0:10]
    return [student_id, name]


def crawl_classroom():
    """crawl_classroom()
    """
    course_ids = []
    owner_ids = []
    for _class_code, _course_id in course_lists.items():
        if options["debug"]:
            print(_class_code, _course_id,
                  course_names[_class_code], course_owners[_class_code])
        course_ids.append(_course_id)
        owner_ids.append(course_owners[_class_code])
    results = []
    if course_ids:
        worker = partial(crawl_classroom_proc, creds_classroom=creds_classroom)
        with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
            for result in tqdm(executor.map(worker, course_ids, owner_ids),
                               total=len(course_ids)):
                results.append(result)
    if results:
        with open(options["outputCsv"], "w") as _f:
            writer = csv.writer(_f, lineterminator="\n")
            # csv indexes
            writer.writerow(
                [
                    "classCode",
                    "SubjectName",
                    "Section",
                    "teacher",
                    "emailAddress",
                    "total",
                    "enroled",
                    "invited",
                    "state"
                ]
            )
            for result in results:
                _class_code = class_codes[result[0]]
                writer.writerow(
                    [
                        _class_code,
                        course_names[_class_code],
                        result[3],
                        class_teachers[_class_code],
                        course_owners[_class_code],
                        int(result[1] + result[2]),
                        result[1],
                        result[2],
                        result[4]
                    ]
                )


def crawl_classroom_proc(_course_id, _owner_id, creds_classroom):
    """crawl_classroom_proc(_course_id, _owner_id, creds_classroom)
    """
    _service = build("classroom", "v1", credentials=creds_classroom)
    page_token = None
    total_enrolled = 0
    while True:
        try:
            _course_students = _service.courses().students().list(
                pageSize=0, courseId=_course_id, pageToken=page_token).execute()
            if "students" in _course_students:
                total_enrolled += len(_course_students.get("students"))
            page_token = _course_students.get('nextPageToken', None)
            if not page_token:
                break
        except HttpError as _e:
            error = json.loads(_e.content).get("error")
            if error.get("code") == 404:  # 404 is not found
                print("Course Not Found {0}".format(_course_id))
                break
            else:
                raise
    page_token = None
    total_invited = 0
    while True:
        _invite_students = _service.invitations().list(
            courseId=_course_id, pageSize=0, pageToken=page_token).execute()
        if "invitations" in _invite_students:
            total_invited += len(_invite_students.get("invitations"))
        # page_token の更新が抜けており、常に1ページ目のみ取得するバグを修正。
        # enrolled students ループと同様に nextPageToken を参照して全ページを取得する。
        page_token = _invite_students.get('nextPageToken', None)
        if not page_token:
            break
    _course_info = _service.courses().get(id=_course_id).execute()
    return [_course_id, total_enrolled, total_invited, _course_info.get("section"), _course_info.get("courseState")]


def get_course_id(_course_id=None):
    """ get_course_id(_course_id=None)
    """
    if options.get("courseId", None):
        _course_id = options["courseId"]
    elif not _course_id:
        return None
    return course_lists.get(_course_id, _course_id)


def get_classroom_stream():
    """get_classroom_stream()
    """
    course_ids = []
    for _class_code, _course_id in course_lists.items():
        print(_class_code, _course_id,
              course_names[_class_code], course_owners[_class_code])
        course_ids.append(_course_id)
    results = []
    if course_ids:
        worker = partial(get_classroom_stream_proc, options=options, creds_classroom=creds_classroom)
        with ProcessPoolExecutor(max_workers=MAX_PROCESS) as executor:
            for result in tqdm(executor.map(worker, course_ids),
                               total=len(course_ids)):
                results.append(result)
    if results:
        with open(options["outputCsv"], "w") as _f:
            writer = csv.writer(_f, lineterminator="\n")
            # csv indexes
            writer.writerow(
                [
                    "classCode",
                    "SubjectName",
                    "teacher",
                    "emailAddress",
                    "announcements"
                ]
            )
            for result in results:
                _class_code = class_codes[result[0]]
                writer.writerow(
                    [
                        _class_code,
                        course_names[_class_code],
                        class_teachers[_class_code],
                        course_owners[_class_code],
                        result[1]
                    ]
                )


def get_classroom_stream_proc(_course_id, options, creds_classroom):
    """get_classroom_stream_proc(_course_id, options, creds_classroom)
    """
    _service = build("classroom", "v1", credentials=creds_classroom)
    page_token = None
    announcements = []
    while True:
        course_announcements = _service.courses().announcements().list(
            pageSize=0, courseId=_course_id, pageToken=page_token).execute()
        if "announcements" in course_announcements:
            announcements.append(course_announcements.get("announcements"))
        page_token = course_announcements.get('nextPageToken', None)
        if not page_token:
            break
    result = ''
    for announcement in announcements:
        for announce in announcement:
            if re.search(options["keyword"], announce['text']):
                result += announce['text'].replace('\n', '')
    return [_course_id, result]


# main()
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './credentials.json'
# max parallel requests for Google Classroom API
# cf. https://developers.google.com/classroom/limits?hl=ja


if __name__ == "__main__":
    MAX_PROCESS = 5
    service = {}
    class_subjects = {}
    class_teachers = {}
    class_sections = {}
    user_emails = {}
    enroll_users = {}
    course_lists = {}
    course_names = {}
    course_owners = {}
    class_codes = {}

    exec_mode, options = parse_options()
    # print(exec_mode, options)
    # load config.ini
    inifile = configparser.ConfigParser()
    inifile.read("./config.ini", "UTF-8")
    adminUser = inifile.get("user", "adminUser")
    admin_id = inifile.get("user", "adminId")
    class_code_regex = inifile.get("user", 'classCodeRegex')
    course_id_file = read_data()
    if not options["dry-run"]:
        file = open(course_id_file, "a")
        csvWrite = csv.writer(file)
    # Google Classroom API activation
    if not options["dry-run"]:
        # Classroom Management scope credentials
        creds_classroom, service_classroom = api_init()
    if exec_mode in ('create', 'default'):
        target = class_subjects
    elif exec_mode == "remove":
        for course_id in options["courses"]:
            print("removing.. {}".format(course_id), end="")
            delete_classroom(course_id)
            print("done")
        sys.exit()
    elif exec_mode == "unenroll":
        delete_user(options["courses"], options["userId"])
        print("done")
        sys.exit()
    elif exec_mode == "lists":
        list_classroom()
        sys.exit()
    elif exec_mode == "info":
        print("courses Information..")
        info_classroom(options["courses"])
        sys.exit()
    elif exec_mode == "user":
        info_user(options["userId"])
        sys.exit()
    elif exec_mode == "crawl":
        crawl_classroom()
        sys.exit()
    elif exec_mode == "getStream":
        get_classroom_stream()
        sys.exit()
    elif exec_mode in ('archive', 'active'):
        update_courses(options["courses"])
        sys.exit()
    elif exec_mode == "owner":
        update_courses(options["courses"], options["owner"])
        sys.exit()
    else:
        target = course_lists
    for class_code in target.keys():
        course_id = course_lists[class_code] if class_code in course_lists else 0
        if exec_mode in ('create', 'default'):
            print("creating..")
            class_teacher = user_emails[class_teachers[class_code]]
            class_subject = class_subjects[class_code] + "(" + class_code + ")"
            classSection = class_sections[class_code]
            if not options["dry-run"]:
                course_id, enroll_code = create_classroom(
                    class_subject, class_sections[class_code], class_teacher
                )
                if (course_id == 0):
                    continue
                csvWrite.writerow(
                    [class_code, course_id, class_subject,
                        class_teacher, enroll_code]
                )
            print("Course    ID:{}".format(course_id))
            print("Class   Code:{}".format(class_code))
            print("Course  Name:{}".format(class_subject))
            print("Subject Name:{}".format(classSection))
            print("Lecturer    :{}".format(class_teacher))
        if exec_mode in ('enroll', 'default'):
            # add adminUser while users are added to a course
            # if enrolling user's class code exist in class_code
            # if options["debug"]:
            #    print('enrollUsers:{0}'.format(enroll_users))
            if class_code in enroll_users:
                if options["debug"]:
                    print('classCode:{}{}'.format(
                        class_code, course_owners[class_code]))
                class_teacher = course_owners[class_code]
                # if invite foreign domain user, adminUser add to class
                if (
                    class_teacher != adminUser and class_teacher != admin_id
                    and not options["dry-run"]
                    and options["foreignDomain"]
                ):
                    add_admin_user(course_id)
                print("Enrolling users.. ", end="")
                if options["foreignDomain"]:
                    invite_users(class_code)
                else:
                    create_users(class_code)
                if (
                    class_teacher != adminUser and class_teacher != admin_id
                    and not options["dry-run"]
                    and options["foreignDomain"]
                ):
                    delete_admin_user(course_id)
    if not options["dry-run"]:
        file.close()
