# coding: UTF-8
from __future__ import print_function
import pickle
import os.path
import sys
import csv
import re
import configparser
from multiprocessing import Pool
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
#
from docopt import docopt
from tqdm import tqdm
import simplejson
import istarmap  # local function

__doc__ = """{f}

Usage:
    {f} all [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {f} create [<classFile>] [--dry-run] [--debug]
    {f} enroll [<enrollFile>] [<coursesFile>] [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {f} unenroll <userId> <courses>... [--dry-run] [--debug]
    {f} remove <courses>... [--dry-run] [--debug]
    {f} lists <outputCsv> [--all-states] [--all-courses] [--debug]
    {f} info <courseId> [--debug]
    {f} crawl <coursesFile> <outputCsv> [--debug]
    {f} get-stream <coursesFile> <keyword> <outputCsv>
    {f} archive <courses>... [--dry-run] [--debug]
    {f} -h | --help

Options:
    all         create new courses and enroll users on the Google Classroom.
    create      create only new courses (default: classes.csv).
    enroll      enroll users on courses (default: enrollments.csv).
                --teacher: invite / enroll Teacher role(default Student role)
                --foreign-domain: force invite mode
    unenroll    unenroll user from courses(course_id1, course_i2, ...).
    remove      remove courses from classroom(course_id1 course_id2 ... ).
    lists       lists of all active courses
                --all-states: include provision and archived courses
                --all-courses: include not following with name conventions
    info        information of course information.
    crawl       display situations of students registration.
    get-stream  get courses stream(announcements) with [keyword]
    archive     change courses(course_id1, course_i2, ...) state to ARCHIVE.
    -h --help   Show this screen and exit.
""".format(
    f=__file__
)


def parse_options():
    """perse_options(void)
    """
    _options = {}
    args = docopt(__doc__)

    _options["classFile"] = args["<classFile>"] if args["<classFile>"] else "classes.csv"
    _options["enrollFile"] = args["<enrollFile>"] if args["<enrollFile>"] else "enrollments.csv"
    _options["courseIdFile"] = args["<coursesFile>"] if args["<coursesFile>"] else "coursesID.csv"
    if args["create"]:
        _exec_mode = "create"
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
        _options["courseId"] = args["<courseId>"]
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
    # !!!!Important!!!!
    scopes = ["https://www.googleapis.com/auth/classroom.courses",
              "https://www.googleapis.com/auth/classroom.rosters",
              "https://www.googleapis.com/auth/classroom.profile.emails",
              "https://www.googleapis.com/auth/classroom.announcements.readonly"]
    # If modifying these scopes, delete the file token.pickle.
    # global service_classroom
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
    # global class_subjects, class_sections, class_teachers
    # global user_emails, enroll_users
    # global course_lists, course_names, course_owners, class_codes
    # global course_id_file
    # set filename configured by the execute option
    _class_file = options["classFile"] if "classFile" in options else "classes.csv"
    _enroll_file = options["enrollFile"] if "enrollFile" in options else "enrollments.csv"
    _course_id_file = options["courseIdFile"] if "courseIdFile" in options else "coursesID.csv"
    # read classes.csv for opened classroom
    # csv format:
    # class_code(Key), subjectName, teacher id, className
    if exec_mode in "create":
        with open(_class_file, "r") as _f:
            # class_subjects = {}
            # class_teachers = {}
            # class_sections = {}
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
            # user_emails = {}
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
            # enroll_users = {}
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
    if exec_mode not in ("create"):
        with open(_course_id_file, "r") as _f:
            # course_lists = {}
            # course_names = {}
            # course_owners = {}
            # class_codes = {}
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
                    class_codes[line[1]] = line[0]  # revese index
                    if len(line) >= 6:
                        # overwrite by couseIdFile
                        class_sections[line[0]] = line[5]
                        class_teachers[line[0]] = line[6]
                    else:
                        class_sections[line[0]] = None
                        class_teachers[line[0]] = None
        return _course_id_file


def create_classroom(_class_subject, _class_section, _class_teacher):
    """ create_classroom(_class_subject, _class_section, _class_teacher)
    """
    # service[_class_teacher] = build(
    #    "classroom", "v1", credentials=creds_classroom)
    try:
        course = {
            "name": _class_subject,
            "ownerId": _class_teacher,
            "section": _class_section,
        }
        course = service_classroom.courses().create(body=course).execute()
        _course_id = course.get("id")
        print("Course created: {0} ({1})".format(
            course.get("name"), _course_id))
        _enroll_code = course.get("enrollmentCode")  # EnrollmentCode
        # if _class_teacher != adminUser:
        #    add_admin_user(_course_id)
    except HttpError as _e:
        error = simplejson.loads(_e.content).get("error")
        if error.get("code") == 403:  # 409 is already exit
            print("Permission Denied")
            _course_id = 0
            _enroll_code = ""
        else:
            raise
    return _course_id, _enroll_code


def add_admin_user(_course_id):
    """add_admin_user(_course_id)
    """
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
        error = simplejson.loads(_e.content).get("error")
        if error.get("code") == 409:  # 409 is already exit
            if options["debug"]:
                print("Already added Admin User")
        elif error.get("code") == 500:  # internal error
            print("Internal error encountered")
        else:
            raise


def delete_admin_user(_course_id):
    """delete_admin_user(_course_id)
    """
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
        error = simplejson.loads(_e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            if options["debug"]:
                print(
                    "Course Admin Teacher {0} is not found".format(_course_id))
        else:
            raise


def delete_user(_course_ids, _user_id):
    """delete_user(_course_id, _user_id)
    """
    for _course_id in _course_ids:
        if options["dry-run"]:
            print("user {0} remove from course {1}".format(
                _user_id, _course_id))
        else:
            try:
                print('unenroll {0} from course id {1}'.format(
                    _user_id, _course_id))
                service_classroom.courses().teachers().delete(
                    courseId=_course_id, userId=_user_id).execute()
            except HttpError as _e:
                error = simplejson.loads(_e.content).get("error")
                if error.get("code") == 404:  # 404 is NOT_FOUND
                    if options["debug"]:
                        print(
                            "{0} is not found in course {1}".format(_user_id, _course_id))
                else:
                    raise


def archive_courses(_course_ids):
    """archive_courses(_course_id)
    """
    for _course_id in _course_ids:
        _course_info = service_classroom.courses().get(id=_course_id).execute()
        body = {
            "id": _course_id,
            "courseState": "ARCHIVED",
            "name": _course_info.get("name")
        }
        if options["dry-run"]:
            print("course {0} is archived".format(_course_id))
        else:
            try:
                print('trying archive course {}...'.format(_course_id))
                service_classroom.courses().update(
                    id=_course_id, body=body).execute()
                print('done')
            except HttpError as _e:
                error = simplejson.loads(_e.content).get("error")
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
    multiple_args = []
    for user_id in enroll_users[class_id]:
        _course_id = course_lists[class_id]
        _invite_user = user_emails[user_id]
        user = {
            "courseId": _course_id,
            "userId": _invite_user,
            "role": _role
        }
        multiple_args.append([user])
        if options["debug"]:
            print([_course_id, user])
#    if not options["dry-run"]:
    results = []
    with Pool(MAX_PROCESS) as pool:
        for result in tqdm(pool.istarmap(invite_users_proc, multiple_args),
                           total=len(enroll_users[class_id])):
            results.append(result)
    for result in results:
        print(result)


def invite_users_proc(user):
    """invite_users_proc(user)
    """
    user_id = user.get("userId")
    _course_id = user.get("courseId")
    if options["debug"]:
        print([_course_id, user_id])
    if not options["dry-run"]:
        # GoogleAPIs are not safe for thread / multiprocessing
        #  due to these are based on httplib2.
        # In this program, each request has a new service instance of GoogleAPI
        if user_id not in service:
            service[user_id] = build(
                "classroom", "v1", credentials=creds_classroom)
        result = 'user={}'.format(user_id)
        try:
            user = service[user_id].invitations().create(body=user).execute()
            result += " invite to {}.".format(_course_id)
        except HttpError as _e:
            error = simplejson.loads(_e.content).get("error")
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
    multiple_args = []
    for user_id in enroll_users[class_id]:
        _course_id = course_lists[class_id]
        _enroll_user = user_emails[user_id]
        print('course_id={}, class_id={}, enrollUser={}'.format(
            _course_id, class_id, _enroll_user))
        user = {
            "userId": _enroll_user,
        }
        multiple_args.append([_course_id, user])
        if options["debug"]:
            print([_course_id, user])
    if not options["dry-run"]:
        with Pool(MAX_PROCESS) as pool:
            for _ in tqdm(pool.istarmap(create_users_proc, multiple_args),
                          total=len(enroll_users[class_id])):
                pass


def create_users_proc(_course_id, user):
    """create_users_proc(_course_id, user)
    """
    if _course_id not in service:
        service[_course_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    try:
        if options["teacherRole"]:
            user = (
                service[_course_id].courses()
                .teachers()
                .create(
                    courseId=_course_id,
                    body=user,
                )
                .execute()
            )
        else:
            user = (
                service[_course_id].courses()
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
        error = simplejson.loads(_e.content).get("error")
        if error.get("code") == 409:
            print(
                "User {0} are already a member of this course.".format(
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
        error = simplejson.loads(_e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            print("Course ID {0} has already been deleted".format(_course_id))
        else:
            raise
    # service_classroom.courses().get(id=_course_id).execute()


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
            # prepare multiple arguments..
            multiple_args = []
            for course in courses:
                multiple_args.append([course])
            # initialize CSV results
            results = []
            # open Multiprocessing Pool
            with Pool(MAX_PROCESS) as pool:
                # Using tqdm() for represent progress bar.
                for result in tqdm(
                        pool.istarmap(list_classroom_proc, multiple_args), total=_total_courses):
                    if result:
                        results.append(result)
            # write csv file.
            writer.writerows(results)


def list_classroom_proc(course):
    """list_classroom_proc(course)
    """
    _course_id = course.get("id")   # notice changed..
    if _course_id not in service:
        service[_course_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    results = service[_course_id].courses().teachers().list(
        courseId=_course_id).execute()
    # print('{}..'.format(course.get('id')), end="")
    # '.*?([0-9]{5}[A-Z][0-9]{4})'
    _class_code = re.match(class_code_regex, course.get("name"))
    _owner_id = course.get("ownerId")
    _teacher_info = service[_course_id].userProfiles().get(
        userId=_owner_id).execute()
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


def info_classroom(_course_id):
    """info_classroom(_course_id)
    """
    _course_info = service_classroom.courses().get(id=_course_id).execute()
    print("course_id: {}".format(_course_info.get("id")))
    print("name    : {}".format(_course_info.get("name")))
    print("section : {}".format(_course_info.get("section")))
    print("status  : {}".format(_course_info.get("courseState")))
    _owner_id = _course_info.get("ownerId")
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


def enrolled_students(_course_id):
    """enrolled_students(_course_id)
    """
    page_token = None
    multiple_args = []
    while True:
        _course_students = service_classroom.courses().students().list(
            pageSize=0, courseId=_course_id, pageToken=page_token).execute()
        if "students" in _course_students:
            for course_student in _course_students.get("students"):
                user_id = course_student.get("profile").get("id")
                multiple_args.append([user_id])
            page_token = _course_students.get('nextPageToken', None)
            if not page_token:
                break
        else:
            break
    results = []
    # if not multiple_args:
    if len(multiple_args):  # old descreption
        with Pool(MAX_PROCESS) as pool:
            for result in tqdm(
                    pool.istarmap(info_classroom_proc, multiple_args), total=len(multiple_args)):
                results.append(result)
    return results


def invited_students(_course_id):
    """invited_students(_course_id)
    """
    page_token = None
    multiple_args = []
    while True:
        _invite_students = service_classroom.invitations().list(
            courseId=_course_id, pageSize=0, pageToken=page_token).execute()
        if "invitations" in _invite_students:
            for _invite_student in _invite_students.get("invitations"):
                user_id = _invite_student.get("userId")
                multiple_args.append([user_id])
            page_token = _invite_students.get('nextPageToken', None)
            if not page_token:
                break
        else:
            break
    results = []
    # if not multiple_args:
    if len(multiple_args):
        with Pool(MAX_PROCESS) as pool:
            for result in tqdm(
                    pool.istarmap(info_classroom_proc, multiple_args), total=len(multiple_args)):
                results.append(result)
    return results


def info_classroom_proc(user_id):
    """info_classroom_proc(user_id)
    """
    if user_id not in service:
        service[user_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    results = service[user_id].userProfiles().get(userId=user_id).execute()
    name = results.get("name").get("fullName")
    student_id = results.get("emailAddress")[0:10]
    return [student_id, name]


def crawl_classroom():
    """crawl_classroom()
    """
    multiple_args = []
    for _class_code, _course_id in course_lists.items():
        if options["debug"]:
            print(_class_code, _course_id,
                  course_names[_class_code], course_owners[_class_code])
        multiple_args.append([_course_id, course_owners[_class_code]])
    results = []
    # if not multiple_args:
    if len(multiple_args):
        with Pool(MAX_PROCESS) as pool:
            for result in tqdm(pool.istarmap(
                    crawl_classroom_proc, multiple_args), total=len(multiple_args)):
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
                ]
            )
            for result in results:
                _class_code = class_codes[result[0]]
                writer.writerow(
                    [
                        _class_code,
                        course_names[_class_code],
                        class_sections[_class_code],
                        class_teachers[_class_code],
                        course_owners[_class_code],
                        int(result[1] + result[2]),
                        result[1],
                        result[2]
                    ]
                )


def crawl_classroom_proc(_course_id, _owner_id):
    """crawl_classroom_proc(_course_id, _owner_id)
    """
    if _course_id not in service:
        service[_course_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    page_token = None
    total_enrolled = 0
    while True:
        try:
            _course_students = service[_course_id].courses().students().list(
                pageSize=0, courseId=_course_id, pageToken=page_token).execute()
            if "students" in _course_students:
                total_enrolled += len(_course_students.get("students"))
            page_token = _course_students.get('nextPageToken', None)
            if not page_token:
                break
        except HttpError as _e:
            error = simplejson.loads(_e.content).get("error")
            if error.get("code") == 404:  # 404 is not found
                print("Course Not Found {0}".format(_course_id))
                break
            else:
                raise
    page_token = None
    total_invited = 0
    while True:
        _invite_students = service[_course_id].invitations().list(
            courseId=_course_id, pageSize=0, pageToken=page_token).execute()
        if "invitations" in _invite_students:
            total_invited += len(_invite_students.get("invitations"))
        if not page_token:
            break
    return [_course_id, total_enrolled, total_invited]


def get_classroom_stream():
    """get_classroom_stream()
    """
    multiple_args = []
    for _class_code, _course_id in course_lists.items():
        print(_class_code, _course_id,
              course_names[_class_code], course_owners[_class_code])
        multiple_args.append([_course_id])
    results = []
    # if not multiple_args:
    if len(multiple_args):
        with Pool(MAX_PROCESS) as pool:
            for result in tqdm(pool.istarmap(get_classroom_stream_proc,
                                             multiple_args), total=len(multiple_args)):
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


def get_classroom_stream_proc(_course_id):
    """get_classroom_stream_proc(_course_id)
    """
    if _course_id not in service:
        service[_course_id] = build(
            "classroom", "v1", credentials=creds_classroom)
    page_token = None
    announcements = []
    while True:
        course_announcements = service[_course_id].courses().announcements().list(
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
    MAX_PROCESS = 10
    service = {}
    # global adminUser, admin_id, class_code_regex
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
#        if options["listAllStates"]:
#            list_classroom()
#        else:
#            list_classroom(course_states="ACTIVE")
        sys.exit()
    elif exec_mode == "info":
        course_id = options["courseId"]
        # class_code_regex = '.*?([0-9]{5}[A-Z][0-9]{4})
        class_code = re.match(class_code_regex, course_id)
        if class_code:
            class_code = class_code.group(1)
            print(class_code)
            if class_code in course_lists:
                print("found")
                course_id = course_lists[class_code]
        print("course{} Information..".format(course_id))
        info_classroom(course_id)
        sys.exit()
    elif exec_mode == "crawl":
        crawl_classroom()
        sys.exit()
    elif exec_mode == "getStream":
        get_classroom_stream()
        sys.exit()
    elif exec_mode == "archive":
        archive_courses(options["courses"])
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
                # create Classroom ownered by class teacher.
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
                # class_teacher = user_emails[class_teachers[class_code]
                #                            ] if class_code in class_teachers else course_owners[class_code]
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
