# coding: UTF-8
from __future__ import print_function
import pickle
import os.path
import simplejson
import csv
import re
import configparser
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
#
from docopt import docopt
from tqdm import tqdm
import istarmap  # local function
from multiprocessing import Pool

__doc__ = """{f}

Usage:
    {f} all [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {f} create [<classFile>] [--dry-run] [--debug]
    {f} enroll [<enrollFile>] [<courseLists>] [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {f} remove <courses>... [--dry-run] [--debug]
    {f} lists <outputCsv> [--all] [--debug]
    {f} info <courseId> [--debug]
    {f} crawl <courseLists> <outputCsv> [--debug]
    {f} get-stream <courseLists> <keyword> <outputCsv>
    {f} -h | --help

Options:
    all         create new courses and enroll users on the Google Classroom.
    create      create only new courses (default: classes.csv).
    enroll      enroll users on courses (default: enrollments.csv).
                --teacher: invite / enroll Teacher role(default Student role)
                --foreign-domain: force invite mode
    remove      remove courses from classroom(courseId1 courseId2 ... ).
    lists       lists of all active courses(--all: include provision courses).
    info        information of course information.
    crawl       display situations of students registration.
    get-stream  get courses stream(announcements) with [keyword]

    -h --help   Show this screen and exit.
""".format(
    f=__file__
)


def parse_options():
    """perse_options(void)
    """
    __options = {}
    args = docopt(__doc__)
    if args["create"]:
        __exec_mode = "create"
        if args["<classFile>"]:
            __options["classFile"] = args["<classFile>"]
    elif args["enroll"]:
        __exec_mode = "enroll"
        if args["--teacher"]:
            __options["teacherRole"] = True
        if args["--foreign-domain"]:
            __options["foreignDomain"] = True
        if args["<enrollFile>"]:
            __options["enrollFile"] = args["<enrollFile>"]
        if args["<courseLists>"]:
            __options["courseIdFile"] = args["<courseLists>"]
    elif args["remove"]:
        __exec_mode = "remove"
        __options["courses"] = args["<courses>"]
    elif args["lists"]:
        __exec_mode = "lists"
        if args["--all"]:
            __options["listAll"] = True
        else:
            __options["listAll"] = False
        __options["outputCsv"] = args["<outputCsv>"]
    elif args["info"]:
        __exec_mode = "info"
        __options["courseId"] = args["<courseId>"]
    elif args["crawl"]:
        __exec_mode = "crawl"
        __options["courseIdFile"] = args["<courseLists>"]
        __options["outputCsv"] = args["<outputCsv>"]
    elif args["get-stream"]:
        __exec_mode = "getStream"
        __options["courseIdFile"] = args["<courseLists>"]
        __options["keyword"] = args["<keyword>"]
        __options["outputCsv"] = args["<outputCsv>"]
    elif args["all"]:
        __exec_mode = "default"
    # print(__exec_mode)
    __options["dry-run"] = True if args["--dry-run"] else False
    __options["debug"] = True if args["--debug"] else False
    if __options["debug"]:
        print("  {0:<20}{1:<20}{2:<20}".format("key", "value", "type"))
        print("  {0:-<60}".format(""))
        for k, v in args.items():
            print("  {0:<20}{1:<20}{2:<20}".format(
                str(k), str(v), str(type(v))))

    return __exec_mode, __options


def api_init():
    """ Initialization of Classroom API for enroll teacher / student to each classroom
    """
    # !!!!Important!!!!
    scopes = ["https://www.googleapis.com/auth/classroom.courses",
              "https://www.googleapis.com/auth/classroom.rosters", "https://www.googleapis.com/auth/classroom.profile.emails", "https://www.googleapis.com/auth/classroom.announcements.readonly"]
    # If modifying these scopes, delete the file token.pickle.
    #global service_classroom
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
    __service_classroom = build("classroom", "v1", credentials=creds)
    return creds, __service_classroom


def read_data():
    """read_data(void)
    """
    global class_subjects, class_sections, classe_tachers
    global user_emails, enroll_users
    global course_lists, courseNames, courseOwners, classCodes

    # set filename configured by the execute option
    __class_file = options["classFile"] if "classFile" in options else "classes.csv"
    __enroll_file = options["enrollFile"] if "enrollFile" in options else "enrollments.csv"
    __course_id_file = options["courseIdFile"] if "courseIdFile" in options else "coursesID.csv"
    # read classes.csv for opened classroom
    # csv format:
    # classCode(Key), subjectName, teacher id, className
    with open(__class_file, "r") as f:
        class_subjects = {}
        classe_tachers = {}
        class_sections = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            try:  # Check duplicated line in classFile
                class_subjects[line[0]]
                continue
            except KeyError:  # first appear line is active
                class_subjects[line[0]] = line[1]
                classe_tachers[line[0]] = line[2]
                class_sections[line[0]] = line[3]
    # read users.csv, getting email address from user id
    # csv format:
    # user id, user Email
    with open("users.csv", "r") as f:
        user_emails = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            user_emails[line[0]] = line[1]
    # read enroll user lists for each class
    # csv format:
    # classCode(Multiple Key), user id
    with open(__enroll_file, "r") as f:
        enroll_users = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            # multiple values for single key
            enroll_users.setdefault(line[0], []).append(line[1])
    # read already created course ID
    # csv format:
    # classCode, Google Classroom course id
    with open(__course_id_file, "r") as f:
        course_lists = {}
        courseNames = {}
        courseOwners = {}
        classCodes = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            if re.match(classCodeRegex, line[0]):  # classCode regex match?
                course_lists[line[0]] = line[1]
                courseNames[line[0]] = line[2]
                courseOwners[line[0]] = line[3]
                classCodes[line[1]] = line[0]  # revese index
                if len(line) >= 6:
                    # overwrite by couseIdFile
                    class_sections[line[0]] = line[5]
                    classe_tachers[line[0]] = line[6]


def create_classroom(classSubject, class_sections, classTeacher):
    # service[classTeacher] = build(
    #    "classroom", "v1", credentials=creds_classroom)
    try:
        course = {
            "name": classSubject,
            "ownerId": classTeacher,
            "section": class_sections,
        }
        course = service_classroom.courses().create(body=course).execute()
        courseId = course.get("id")
        print("Course created: {0} ({1})".format(course.get("name"), courseId))
        enrollCode = course.get("enrollmentCode")  # EnrollmentCode
        # if classTeacher != adminUser:
        #    add_admin_user(courseId)
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 403:  # 409 is already exit
            print("Permission Denied")
            courseId = 0
            enrollCode = ""
        else:
            raise
    return courseId, enrollCode


def add_admin_user(courseId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=creds_classroom)
    teacher = {"userId": "me"}
    try:
        teacher = (
            service[courseId].courses()
            .teachers()
            .create(courseId=courseId, body=teacher)
            .execute()
        )
        if options["debug"]:
            print("Course {0} add Admin User".format(courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 409:  # 409 is already exit
            if options["debug"]:
                print("Already added Admin User")
        elif error.get("code") == 500:  # internal error
            print("Internal error encountered")
        else:
            raise


def delete_admin_user(courseId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=creds_classroom)
    try:
        service[courseId].courses().teachers().delete(
            courseId=courseId, userId="me"
        ).execute()
        if options["debug"]:
            print("Course {0} delete Admin User".format(courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            if options["debug"]:
                print("Course Admin Teacher {0} is not found".format(courseId))
        else:
            raise


def invite_users(classId):
    Role = 'TEACHER' if 'teacherRole' in options else 'STUDENT'
    multipleArgs = []
    for userId in enroll_users[classId]:
        courseId = course_lists[classId]
        inviteUser = user_emails[userId]
        user = {
            "courseId": courseId,
            "userId": inviteUser,
            "role": Role
        }
        multipleArgs.append([user])
    results = []
    with Pool(maxProcess) as pool:
        for result in tqdm(pool.istarmap(invite_users_proc, multipleArgs), total=len(enroll_users[classId])):
            results.append(result)
    for result in results:
        print(result)


def invite_users_proc(user):
    userId = user.get("userId")
    courseId = user.get("courseId")
    # GoogleAPIs are not safe for thread / multiprocessing
    #  due to these are based on httplib2.
    # In this program, each request has a new service instance of GoogleAPI
    if userId not in service:
        service[userId] = build("classroom", "v1", credentials=creds_classroom)
    result = 'user={}'.format(userId)
    try:
        user = service[userId].invitations().create(body=user).execute()
        result += " is enrolled to {}.".format(courseId)
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 409:
            result += " is already a invite to ({}).".format(courseId)
        elif error.get("code") == 400:
            result += " is already a member of ({}).".format(courseId)
        elif error.get("code") == 401:
            print("Authentication error")
        else:
            raise
    return result


def create_users(classId):
    multipleArgs = []
    for userId in enroll_users[classId]:
        courseId = course_lists[classId]
        enrollUser = user_emails[userId]
        print('courseId={}, classId={}, inviteUser={}'.format(
            courseId, classId, enrollUser))
        user = {
            "userId": enrollUser,
        }
        multipleArgs.append([courseId, user])
        print([courseId, user])
    with Pool(maxProcess) as pool:
        for _ in tqdm(pool.istarmap(create_users_proc, multipleArgs), total=len(enroll_users[classId])):
            pass


def create_users_proc(courseId, user):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=creds_classroom)
    try:
        if 'teacherRole' in options:
            user = (
                service[courseId].courses()
                .teachers()
                .create(
                    courseId=courseId,
                    body=user,
                )
                .execute()
            )
        else:
            user = (
                service[courseId].courses()
                .students()
                .create(
                    courseId=courseId,
                    body=user,
                )
                .execute()
            )
        print(
            'User {0} was enrolled as a user in the course with ID "{1}"'.format(
                user.get("profile").get("name").get("fullName"), courseId
            )
        )
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 409:
            print(
                "User {0} are already a member of this course.".format(
                    user.get("userId")
                )
            )
        elif error.get("code") == 403:
            print("...Permission Denied.")
        else:
            print(error.get("code"))
            raise


def delete_classroom(courseId):
    try:
        service_classroom.courses().delete(id=courseId).execute()
        print("Course {0} has been removed".format(courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            print("Course ID {0} has already been deleted".format(courseId))
        else:
            raise
    # service_classroom.courses().get(id=courseId).execute()


def list_classroom(courseStates=None):
    pageToken = None
    courses = []
    while True:
        results = service_classroom.courses().list(pageSize=0, pageToken=pageToken,
                                                   courseStates=courseStates).execute()
        # if set pageSize=0, 500 responses are max queue( at 2020.05.06 )
        pageToken = results.get('nextPageToken', None)
        courses += results.get("courses", [])
        if not pageToken:
            break
    if not courses:
        print("No courses found")
    else:
        totalCourses = len(courses)
        print("total Courses: {} ".format(totalCourses))
        with open(options["outputCsv"], "w") as f:
            writer = csv.writer(f, lineterminator="\n")
            # csv indexes
            writer.writerow(
                [
                    "classCode",
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
            multipleArgs = []
            for course in courses:
                multipleArgs.append([course])
            # initialize CSV results
            results = []
            # open Multiprocessing Pool
            with Pool(maxProcess) as pool:
                # Using tqdm() for represent progress bar.
                for result in tqdm(
                    pool.istarmap(list_classroom_proc, multipleArgs), total=totalCourses
                ):
                    if result:
                        results.append(result)
            # write csv file.
            writer.writerows(results)


def list_classroom_proc(course):
    courseId = course.get("id")   # notice changed..
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=creds_classroom)
    results = service[courseId].courses().teachers().list(
        courseId=courseId).execute()
    # print('{}..'.format(course.get('id')), end="")
    # '.*?([0-9]{5}[A-Z][0-9]{4})'
    classCode = re.match(classCodeRegex, course.get("name"))
    ownerId = course.get("ownerId")
    teacherInfo = service[courseId].userProfiles().get(
        userId=ownerId).execute()
    teachers = results.get("teachers", [])
    teacherName = ""
    for teacher in teachers:
        teacherName += "/" + str(teacher["profile"]["name"]["fullName"])
    if classCode:
        return [
            classCode.group(1),
            course.get("id"),
            course.get("name"),
            teacherInfo.get("emailAddress"),
            course.get("ownerId"),
            course.get("section"),
            teacherName.lstrip("/"),
            course.get("enrollmentCode"),
            course.get("courseState"),
        ]
    else:
        False


def info_classroom(courseId):
    courseInfo = service_classroom.courses().get(id=courseId).execute()
    print("courseID: {}".format(courseInfo.get("id")))
    print("name    : {}".format(courseInfo.get("name")))
    print("section : {}".format(courseInfo.get("section")))
    print("status  : {}".format(courseInfo.get("courseState")))
    ownerId = courseInfo.get("ownerId")
    teacherInfo = service_classroom.userProfiles().get(userId=ownerId).execute()
    print("owner : {}({})".format(teacherInfo.get(
        "emailAddress"), teacherInfo.get("name").get("fullName")))
    results = service_classroom.courses().teachers().list(
        courseId=courseId).execute()
    teachers = results.get("teachers", [])
    teacherName = ""
    for teacher in teachers:
        teacherName += "/" + str(teacher["profile"]["name"]["fullName"])
    print("teacher : {}".format(teacherName))
    if (ownerId != adminId):
        add_admin_user(courseId)
    print("Enrolled user lists...")
    results = enrolled_students(courseId)
    if results:
        for result in sorted(results):
            print("{},{}".format(result[0], result[1]))
    print("Inviting user lists...")
    results = invited_students(courseId)
    if results:
        for result in sorted(results):
            print("{},{}".format(result[0], result[1]))
    if (ownerId != adminId):
        delete_admin_user(courseId)


def enrolled_students(courseId):
    pageToken = None
    multipleArgs = []
    while True:
        courseStudents = service_classroom.courses().students().list(
            pageSize=0, courseId=courseId, pageToken=pageToken).execute()
        if "students" in courseStudents:
            for courseStudent in courseStudents.get("students"):
                userId = courseStudent.get("profile").get("id")
                multipleArgs.append([userId])
            pageToken = courseStudents.get('nextPageToken', None)
            if not pageToken:
                break
        else:
            break
    results = []
    if len(multipleArgs):
        with Pool(maxProcess) as pool:
            for result in tqdm(pool.istarmap(info_classroom_proc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    return results


def invited_students(courseId):
    pageToken = None
    multipleArgs = []
    while True:
        inviteStudents = service_classroom.invitations().list(
            courseId=courseId, pageSize=0, pageToken=pageToken).execute()
        if "invitations" in inviteStudents:
            for inviteStudent in inviteStudents.get("invitations"):
                userId = inviteStudent.get("userId")
                multipleArgs.append([userId])
            pageToken = inviteStudents.get('nextPageToken', None)
            if not pageToken:
                break
        else:
            break
    results = []
    if len(multipleArgs):
        with Pool(maxProcess) as pool:
            for result in tqdm(pool.istarmap(info_classroom_proc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    return results


def info_classroom_proc(userId):
    if userId not in service:
        service[userId] = build("classroom", "v1", credentials=creds_classroom)
    results = service[userId].userProfiles().get(userId=userId).execute()
    name = results.get("name").get("fullName")
    studentId = results.get("emailAddress")[0:10]
    return [studentId, name]


def crawl_classroom():
    multipleArgs = []
    for classCode, courseId in course_lists.items():
        print(classCode, courseId,
              courseNames[classCode], courseOwners[classCode])
        multipleArgs.append([courseId, courseOwners[classCode]])
    results = []
    if len(multipleArgs):
        with Pool(maxProcess) as pool:
            for result in tqdm(pool.istarmap(crawl_classroom_proc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    if results:
        with open(options["outputCsv"], "w") as f:
            writer = csv.writer(f, lineterminator="\n")
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
                classCode = classCodes[result[0]]
                writer.writerow([classCode, courseNames[classCode], class_sections[classCode], classe_tachers[classCode],
                                 courseOwners[classCode], int(result[1]+result[2]), result[1], result[2]])


def crawl_classroom_proc(courseId, ownerId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=creds_classroom)
    pageToken = None
    totalEnrolled = 0
    while True:
        courseStudents = service[courseId].courses().students().list(
            pageSize=0, courseId=courseId, pageToken=pageToken).execute()
        if "students" in courseStudents:
            totalEnrolled += len(courseStudents.get("students"))
        pageToken = courseStudents.get('nextPageToken', None)
        if not pageToken:
            break
    pageToken = None
    totalInvited = 0
    while True:
        inviteStudents = service[courseId].invitations().list(
            courseId=courseId, pageSize=0, pageToken=pageToken).execute()
        if "invitations" in inviteStudents:
            totalInvited += len(inviteStudents.get("invitations"))
        if not pageToken:
            break
    return [courseId, totalEnrolled, totalInvited]


def get_classroom_stream():
    multipleArgs = []
    for classCode, courseId in course_lists.items():
        print(classCode, courseId,
              courseNames[classCode], courseOwners[classCode])
        multipleArgs.append([courseId])
    results = []
    if len(multipleArgs):
        with Pool(maxProcess) as pool:
            for result in tqdm(pool.istarmap(get_classroom_stream_proc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    if results:
        with open(options["outputCsv"], "w") as f:
            writer = csv.writer(f, lineterminator="\n")
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
                classCode = classCodes[result[0]]
                writer.writerow([classCode, courseNames[classCode],
                                 classe_tachers[classCode], courseOwners[classCode], result[1]])


def get_classroom_stream_proc(courseId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=creds_classroom)
    pageToken = None
    announcements = []
    while True:
        courseAnnouncements = service[courseId].courses().announcements().list(
            pageSize=0, courseId=courseId, pageToken=pageToken).execute()
        if "announcements" in courseAnnouncements:
            announcements.append(courseAnnouncements.get("announcements"))
        pageToken = courseAnnouncements.get('nextPageToken', None)
        if not pageToken:
            break
    result = ''
    for announcement in announcements:
        for announce in announcement:
            if re.search(options["keyword"], announce['text']):
                result += announce['text'].replace('\n', '')
    return [courseId, result]


# main()
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './credentials.json'
courseIdFile = "coursesID.csv"
# max parallel requests for Google Classroom API
# cf. https://developers.google.com/classroom/limits?hl=ja
maxProcess = 10
service = {}


if __name__ == "__main__":
    global adminUser, adminId, classCodeRegex
    global options
    global creds_classroom
    global service_classroom
    global class_subjects, class_sections, classe_tachers
    global user_emails, enroll_users
    global course_lists, courseNames, courseOwners, classCodes
    exec_mode, options = parse_options()
    # print(exec_mode, options)
    # load config.ini
    inifile = configparser.ConfigParser()
    inifile.read("./config.ini", "UTF-8")
    adminUser = inifile.get("user", "adminUser")
    adminId = inifile.get("user", "adminId")
    classCodeRegex = inifile.get("user", 'classCodeRegex')
    read_data()
    if not options["dry-run"]:
        file = open(courseIdFile, "a")
        csvWrite = csv.writer(file)
    # Google Classroom API activation
    if not options["dry-run"]:
        # Classroom Management scope credentials
        creds_classroom, service_classroom = api_init()
    if exec_mode == "create" or exec_mode == "default":
        target = class_subjects
    elif exec_mode == "remove":
        for courseId in options["courses"]:
            print("removing.. {}".format(courseId), end="")
            delete_classroom(courseId)
            print("done")
        exit()
    elif exec_mode == "lists":
        if options["listAll"]:
            list_classroom()
        else:
            list_classroom(courseStates="ACTIVE")
        exit()
    elif exec_mode == "info":
        courseId = options["courseId"]
        # classCodeRegex = '.*?([0-9]{5}[A-Z][0-9]{4})
        classCode = re.match(classCodeRegex, courseId)
        if classCode:
            classCode = classCode.group(1)
            print(classCode)
            if classCode in course_lists:
                print("found")
                courseId = course_lists[classCode]
        print("course{} Information..".format(courseId))
        info_classroom(courseId)
        exit()
    elif exec_mode == "crawl":
        crawl_classroom()
        exit()
    elif exec_mode == "getStream":
        get_classroom_stream()
        exit()
    else:
        target = course_lists
    for classCode in target.keys():
        courseId = course_lists[classCode] if classCode in course_lists else 0
        if exec_mode == "create" or exec_mode == "default":
            print("creating..")
            classTeacher = user_emails[classe_tachers[classCode]]
            classSubject = class_subjects[classCode] + "(" + classCode + ")"
            classSection = class_sections[classCode]
            if not options["dry-run"]:
                # create Classroom ownered by class teacher.
                courseId, enrollCode = create_classroom(
                    classSubject, class_sections[classCode], classTeacher
                )
                if (courseId == 0):
                    continue
                csvWrite.writerow(
                    [classCode, courseId, classSubject, classTeacher, enrollCode]
                )
            print("Course    ID:{}".format(courseId))
            print("Class   Code:{}".format(classCode))
            print("Course  Name:{}".format(classSubject))
            print("Subject Name:{}".format(classSection))
            print("Lecturer    :{}".format(classTeacher))
        if exec_mode == "enroll" or exec_mode == "default":
            # add adminUser while users are added to a course
            # if enrolling user's class code exist in classCode
            if classCode in enroll_users:
                classTeacher = user_emails[classe_tachers[classCode]
                                           ] if classCode in classe_tachers else courseOwners[classCode]
                if (
                    classTeacher != adminUser and classTeacher != adminId
                    and not options["dry-run"]
                    and "foreignDomain" in options
                ):
                    add_admin_user(courseId)
                    pass
                if not options["dry-run"]:
                    print("Enrolling users.. ", end="")
                    if "foreignDomain" in options:
                        invite_users(classCode)
                    else:
                        create_users(classCode)
                if (
                    classTeacher != adminUser and classTeacher != adminId
                    and not options["dry-run"]
                    and "foreignDomain" in options
                ):
                    pass
                    delete_admin_user(courseId)
    if not options["dry-run"]:
        file.close()
