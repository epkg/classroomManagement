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
    {f} create [<class_file>] [--dry-run] [--debug]
    {f} enroll [<enroll_file>] [<course_lists>] [--dry-run] [--teacher] [--foreign-domain] [--debug]
    {f} remove <courses>... [--dry-run] [--debug]
    {f} lists <output_csv> [--debug]
    {f} info <course_id> [--debug]
    {f} crawl <course_lists> <output_csv>[--debug]
    {f} -h | --help

Options:
    all         create new courses and enroll users on the Google Classroom.
    create      create only new courses (default: classes.csv).
    enroll      enroll users on courses (default: enrollments.csv).
                --teacher: invite / enroll Teacher role(default Student role)
                --foreign-domain: force invite mode
    remove      remove courses from classroom(courseId1 courseId2 ... ).
    lists       lists of all courses.
    info        information of course information.
    crawl       display situations of students registration.

    -h --help   Show this screen and exit.
""".format(
    f=__file__
)


def parseOptions():
    args = docopt(__doc__)
    options = {}
    if args["create"]:
        execMode = "create"
        if args["<class_file>"]:
            options["classFile"] = args["<class_file>"]
    elif args["enroll"]:
        execMode = "enroll"
        if args["--teacher"]:
            options["teacherRole"] = True
        if args["--foreign-domain"]:
            options["foreignDomain"] = True
        if args["<enroll_file>"]:
            options["enrollFile"] = args["<enroll_file>"]
        if args["<course_lists>"]:
            options["courseIdFile"] = args["<course_lists>"]
    elif args["remove"]:
        execMode = "remove"
        options["courses"] = args["<courses>"]
    elif args["lists"]:
        execMode = "lists"
        options["output_csv"] = args["<output_csv>"]
    elif args["info"]:
        execMode = "info"
        options["courseId"] = args["<course_id>"]
    elif args["crawl"]:
        execMode = "crawl"
        options["courseIdFile"] = args["<course_lists>"]
        options["output_csv"] = args["<output_csv>"]
    elif args["all"]:
        execMode = "default"
    # print(execMode)
    options["dry-run"] = True if args["--dry-run"] else False
    options["debug"] = True if args["--debug"] else False
    if options["debug"]:
        print("  {0:<20}{1:<20}{2:<20}".format("key", "value", "type"))
        print("  {0:-<60}".format(""))
        for k, v in args.items():
            print("  {0:<20}{1:<20}{2:<20}".format(
                str(k), str(v), str(type(v))))

    return execMode, options


def api_init():
    """ Initialization of Classroom API for enroll teacher / student to each classroom
    """
    # !!!!Important!!!!
    SCOPES = ["https://www.googleapis.com/auth/classroom.courses",
              "https://www.googleapis.com/auth/classroom.rosters", "https://www.googleapis.com/auth/classroom.profile.emails"]
    # If modifying these scopes, delete the file token.pickle.
    global serviceClassroom
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
                "credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    serviceClassroom = build("classroom", "v1", credentials=creds)
    return creds


def readData():
    global classSubjects, classSections, classTeachers
    global userEmails
    global enrollUsers
    global courseLists, courseNames, courseOwners, classCodes

    # set filename configured by the execute option
    classFile = options["classFile"] if "classFile" in options else "classes.csv"
    enrollFile = options["enrollFile"] if "enrollFile" in options else "enrollments.csv"
    courseIdFile = options["courseIdFile"] if "courseIdFile" in options else "coursesID.csv"
    # read classes.csv for opened classroom
    # csv format:
    # classCode(Key), subjectName, teacher id, className
    with open(classFile, "r") as f:
        classSubjects = {}
        classTeachers = {}
        classSections = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            classSubjects[line[0]] = line[1]
            classTeachers[line[0]] = line[2]
            classSections[line[0]] = line[3]
    # read users.csv, getting email address from user id
    # csv format:
    # user id, user Email
    with open("users.csv", "r") as f:
        userEmails = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            userEmails[line[0]] = line[1]
    # read enroll user lists for each class
    # csv format:
    # classCode(Multiple Key), user id
    with open(enrollFile, "r") as f:
        enrollUsers = {}
        for line in f:
            if line == "\n":
                continue
            line = line.rstrip("\n").split(",")
            if(line[0][0] == "#"):
                continue
            # multiple values for single key
            enrollUsers.setdefault(line[0], []).append(line[1])
    # read already created course ID
    # csv format:
    # classCode, Google Classroom course id
    with open(courseIdFile, "r") as f:
        courseLists = {}
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
                courseLists[line[0]] = line[1]
                courseNames[line[0]] = line[2]
                courseOwners[line[0]] = line[3]
                classCodes[line[1]] = line[0]  # revese index
                if len(line) >= 6:
                    # overwrite by couseIdFile
                    classSections[line[0]] = line[5]
                    classTeachers[line[0]] = line[6]


def createClassroom(classSubject, classSections, classTeacher):
    course = {
        "name": classSubject,
        "ownerId": classTeacher,
        "section": classSections,
    }
    course = serviceClassroom.courses().create(body=course).execute()
    courseId = course.get("id")
    print("Course created: {0} ({1})".format(course.get("name"), courseId))
    enrollCode = course.get("enrollmentCode")  # EnrollmentCode
    # if classTeacher != adminUser:
    #    addAdminUser(courseId)
    return courseId, enrollCode


def addAdminUser(courseId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=credsClassroom)
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


def deleteAdminUser(courseId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=credsClassroom)
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


def inviteUsers(classId):
    Role = 'TEACHER' if 'teacherRole' in options else 'STUDENT'
    multipleArgs = []
    for userId in enrollUsers[classId]:
        courseId = courseLists[classId]
        inviteUser = userEmails[userId]
        user = {
            "courseId": courseId,
            "userId": inviteUser,
            "role": Role
        }
        multipleArgs.append([user])
    results = []
    with Pool(maxProcess) as pool:
        for result in tqdm(pool.istarmap(inviteUsersProc, multipleArgs), total=len(enrollUsers[classId])):
            results.append(result)
    for result in results:
        print(result)


def inviteUsersProc(user):
    userId = user.get("userId")
    courseId = user.get("courseId")
    # GoogleAPIs are not safe for thread / multiprocessing
    #  due to these are based on httplib2.
    # In this program, each request has a new service instance of GoogleAPI
    if userId not in service:
        service[userId] = build("classroom", "v1", credentials=credsClassroom)
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


def createUsers(classId):
    multipleArgs = []
    for userId in enrollUsers[classId]:
        courseId = courseLists[classId]
        enrollUser = userEmails[userId]
        print('courseId={}, classId={}, inviteUser={}'.format(
            courseId, classId, enrollUser))
        user = {
            "userId": enrollUser,
        }
        multipleArgs.append([courseId, user])
        print([courseId, user])
    with Pool(maxProcess) as pool:
        for _ in tqdm(pool.istarmap(createUsersProc, multipleArgs), total=len(enrollUsers[classId])):
            pass


def createUsersProc(courseId, user):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=credsClassroom)
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


def deleteClassroom(courseId):
    try:
        serviceClassroom.courses().delete(id=courseId).execute()
        print("Course {0} has been removed".format(courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get("error")
        if error.get("code") == 404:  # 404 is NOT_FOUND
            print("Course ID {0} has already been deleted".format(courseId))
        else:
            raise
    # serviceClassroom.courses().get(id=courseId).execute()


def listClassroom(courseStates=None):
    pageToken = None
    courses = []
    while True:
        results = serviceClassroom.courses().list(pageSize=0, pageToken=pageToken,
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
        with open(options["output_csv"], "w") as f:
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
                    pool.istarmap(listClassroomProc, multipleArgs), total=totalCourses
                ):
                    if result:
                        results.append(result)
            # write csv file.
            writer.writerows(results)


def listClassroomProc(course):
    courseId = course.get("id")   # notice changed..
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=credsClassroom)
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


def infoClassroom(courseId):
    courseInfo = serviceClassroom.courses().get(id=courseId).execute()
    print("courseID: {}".format(courseInfo.get("id")))
    print("name    : {}".format(courseInfo.get("name")))
    print("section : {}".format(courseInfo.get("section")))
    print("status  : {}".format(courseInfo.get("courseState")))
    ownerId = courseInfo.get("ownerId")
    teacherInfo = serviceClassroom.userProfiles().get(userId=ownerId).execute()
    print("teacher : {}({})".format(teacherInfo.get(
        "emailAddress"), teacherInfo.get("name").get("fullName")))
    if (ownerId != adminId):
        addAdminUser(courseId)
    print("Enrolled user lists...")
    results = enrolledStudents(courseId)
    if results:
        for result in sorted(results):
            print("{},{}".format(result[0], result[1]))
    print("Inviting user lists...")
    results = invitedStudents(courseId)
    if results:
        for result in sorted(results):
            print("{},{}".format(result[0], result[1]))
    if (ownerId != adminId):
        deleteAdminUser(courseId)


def enrolledStudents(courseId):
    pageToken = None
    multipleArgs = []
    while True:
        courseStudents = serviceClassroom.courses().students().list(
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
            for result in tqdm(pool.istarmap(infoClassroomProc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    return results


def invitedStudents(courseId):
    pageToken = None
    multipleArgs = []
    while True:
        inviteStudents = serviceClassroom.invitations().list(
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
            for result in tqdm(pool.istarmap(infoClassroomProc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    return results


def infoClassroomProc(userId):
    if userId not in service:
        service[userId] = build("classroom", "v1", credentials=credsClassroom)
    results = service[userId].userProfiles().get(userId=userId).execute()
    name = results.get("name").get("fullName")
    studentId = results.get("emailAddress")[0:10]
    return [studentId, name]


def crawlClassroom():
    multipleArgs = []
    for classCode, courseId in courseLists.items():
        print(classCode, courseId,
              courseNames[classCode], courseOwners[classCode])
        multipleArgs.append([courseId, courseOwners[classCode]])
    results = []
    if len(multipleArgs):
        with Pool(maxProcess) as pool:
            for result in tqdm(pool.istarmap(crawlClassroomProc, multipleArgs), total=len(multipleArgs)):
                results.append(result)
    if results:
        with open(options["output_csv"], "w") as f:
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
                writer.writerow([classCode, courseNames[classCode], classSections[classCode], classTeachers[classCode],
                                 courseOwners[classCode], int(result[1]+result[2]), result[1], result[2]])


def crawlClassroomProc(courseId, ownerId):
    if courseId not in service:
        service[courseId] = build(
            "classroom", "v1", credentials=credsClassroom)
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


# main()
#os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './credentials.json'
courseIdFile = "coursesID.csv"
# max parallel requests for Google Classroom API
# cf. https://developers.google.com/classroom/limits?hl=ja
maxProcess = 10
service = {}


if __name__ == "__main__":
    global adminUser, adminId, classCodeRegex
    global options
    global credsClassroom
    execMode, options = parseOptions()
    # print(execMode, options)
    # load config.ini
    inifile = configparser.ConfigParser()
    inifile.read("./config.ini", "UTF-8")
    adminUser = inifile.get("user", "adminUser")
    adminId = inifile.get("user", "adminId")
    classCodeRegex = inifile.get("user", 'classCodeRegex')
    readData()
    if not options["dry-run"]:
        file = open(courseIdFile, "a")
        csvWrite = csv.writer(file)
    # Google Classroom API activation
    if not options["dry-run"]:
        credsClassroom = api_init()  # Classroom Management scope credentials
    if execMode == "create" or execMode == "default":
        target = classSubjects
    elif execMode == "remove":
        for courseId in options["courses"]:
            print("removing.. {}".format(courseId), end="")
            deleteClassroom(courseId)
            print("done")
        exit()
    elif execMode == "lists":
        listClassroom(courseStates="ACTIVE")
        exit()
    elif execMode == "info":
        courseId = options["courseId"]
        # classCodeRegex = '.*?([0-9]{5}[A-Z][0-9]{4})
        classCode = re.match(classCodeRegex, courseId)
        if classCode:
            classCode = classCode.group(1)
            print(classCode)
            if classCode in courseLists:
                print("found")
                courseId = courseLists[classCode]
        print("course{} Information..".format(courseId))
        infoClassroom(courseId)
        exit()
    elif execMode == "crawl":
        crawlClassroom()
        exit()
    else:
        target = courseLists
    for classCode in target.keys():
        courseId = courseLists[classCode] if classCode in courseLists else 0
        if execMode == "create" or execMode == "default":
            print("creating..")
            if not options["dry-run"]:
                classTeacher = userEmails[classTeachers[classCode]]
                classSubject = classSubjects[classCode] + "(" + classCode + ")"
                classSection = classSections[classCode]
                # create Classroom ownered by class teacher.
                courseId, enrollCode = createClassroom(
                    classSubject, classSections[classCode], classTeacher
                )
                csvWrite.writerow(
                    [classCode, courseId, classSubject, classTeacher, enrollCode]
                )
            print("Course    ID:{}".format(courseId))
            print("Class   Code:{}".format(classCode))
            print("Course  Name:{}".format(classSubject))
            print("Subject Name:{}".format(classSection))
            print("Lecturer    :{}".format(classTeacher))
        if execMode == "enroll" or execMode == "default":
            # add adminUser while users are added to a course
            # if enrolling user's class code exist in classCode
            if classCode in enrollUsers:
                classTeacher = userEmails[classTeachers[classCode]
                                          ] if classCode in classTeachers else courseOwners[classCode]
                if (
                    classTeacher != adminUser and classTeacher != adminId
                    and not options["dry-run"]
                    and "foreignDomain" in options
                ):
                    addAdminUser(courseId)
                    pass
                if not options["dry-run"]:
                    print("Enrolling users.. ", end="")
                    if "foreignDomain" in options:
                        inviteUsers(classCode)
                    else:
                        createUsers(classCode)
                if (
                    classTeacher != adminUser and classTeacher != adminId
                    and not options["dry-run"]
                    and "foreignDomain" in options
                ):
                    pass
                    deleteAdminUser(courseId)
    if not options["dry-run"]:
        file.close()
