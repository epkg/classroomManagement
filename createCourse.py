# coding: UTF-8
from __future__ import print_function
import pickle
import os.path
import simplejson
import csv
import configparser
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from docopt import docopt
from tqdm import tqdm

__doc__ = """{f}

Usage:
    {f} all [--dry-run]
    {f} create [<class_file>] [--dry-run]
    {f} enroll [<enroll_file>] [--dry-run]
    {f} remove <courses>... [--dry-run]
    {f} lists <output_csv>
    {f} info <course_id>
    {f} -h | --help

Options:
    all         create new courses and enroll students on the Google Classroom.
    create      create only new courses (default: classes.csv).
    enroll      enroll students on courses (default: enrollments.csv).
    remove      remove courses from classroom(courseId1 courseId2 ... ).
    lists       lists of all courses.
    info        information of course information.

    -h --help   Show this screen and exit.
""".format(f=__file__)


def parseOptions():
    args = docopt(__doc__)
#    print("  {0:<20}{1:<20}{2:<20}".format("key", "value", "type"))
#    print("  {0:-<60}".format(""))
#    for k,v in args.items():
#       print("  {0:<20}{1:<20}{2:<20}".format(str(k), str(v), str(type(v))))
    options = {}
    if args['create']:
        execMode = 'create'
        if args['<class_file>']:
            options['classFile'] = args['<class_file>']
    elif args['enroll']:
        execMode = 'enroll'
        if args['<enroll_file>']:
            options['enrollFile'] = args['<enroll_file>']
    elif args['remove']:
        execMode = 'remove'
        options['courses'] = args['courses']
    elif args['lists']:
        execMode = 'lists'
        options['output_csv'] = args['<output_csv>']
    elif args['info']:
        execMode = 'info'
        options['courseId'] = args['<course_id>']
    elif args['all']:
        execMode = 'default'
    # print(execMode)
    options['dry-run'] = True if args['--dry-run'] else False
    return execMode, options


def api_init_class():
    """ Initialization of Classroom API for create classroom
    """
    # !!!!Important!!!!
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/classroom.courses']
    # cf. Authorize Request https://developers.google.com/classroom/guides/auth
    global serviceClassroom
    creds = None
    # The file token.*.pickle stores the user's access and refresh tokens, and
    # is created automatically when the authorization flow completes for the
    # first time.
    if os.path.exists('token.create_class.pickle'):
        with open('token.create_class.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.create_class.pickle', 'wb') as token:
            pickle.dump(creds, token)

    serviceClassroom = build('classroom', 'v1', credentials=creds)


def api_init_enroll():
    """ Initialization of Classroom API for enroll teacher / student to each classroom
    """
    # !!!!Important!!!!
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/classroom.rosters']
    global serviceEnrollment
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.enroll.pickle'):
        with open('token.enroll.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.enroll.pickle', 'wb') as token:
            pickle.dump(creds, token)

    serviceEnrollment = build('classroom', 'v1', credentials=creds)


def readData():
    global classSubjects, classSections, classTeachers
    global studentEmails
    global enrollStudents
    global courseLists

    # set filename configured by the execute option
    classFile = options['classFile'] if 'classFile' in options else "classes.csv"
    enrollFile = options['enrollFile'] if 'enrollFile' in options else "enrollments.csv"
    # read classes.csv for opened classroom
    # csv format:
    # classCode(Key), subjectName, teacher id, className
    with open(classFile, 'r') as f:
        classSubjects = {}
        classTeachers = {}
        classSections = {}
        for line in f:
            line = line.rstrip('\n').split(',')
            classSubjects[line[0]] = line[1]
            classTeachers[line[0]] = line[2]
            classSections[line[0]] = line[3]
    # read students.csv, getting email address from students id
    # csv format:
    # student id, student Email
    with open('students.csv', 'r') as f:
        studentEmails = {}
        for line in f:
            line = line.rstrip('\n').split(',')
            studentEmails[line[0]] = line[1]
    # read enroll student lists for each class
    # csv format:
    # classCode(Multiple Key), student id
    with open(enrollFile, 'r') as f:
        enrollStudents = {}
        for line in f:
            line = line.rstrip('\n').split(',')
            # multiple values for single key
            enrollStudents.setdefault(line[0], []).append(line[1])
    # read already created course ID
    # csv format:
    # classCode, Google Classroom course id
    with open('coursesID.csv', 'r') as f:
        courseLists = {}
        for line in f:
            line = line.rstrip('\n').split(',')
            courseLists[line[0]] = line[1]


def createClassroom(classSubject, classSections, classTeacher):
    course = {
        'name': classSubject,
        'ownerId': classTeacher,
        'section': classSections,
    }
    course = serviceClassroom.courses().create(body=course).execute()
    courseId = course.get('id')
    print(u'Course created: {0} ({1})'.format(course.get('name'),
                                              courseId))
    enrollCode = course.get('enrollmentCode')  # EnrollmentCode
    # if classTeacher != adminUser:
    #    addAdminUser(courseId)
    return courseId, enrollCode


def addAdminUser(courseId):
    teacher = {
        'userId': adminUser
    }
    teacher = serviceEnrollment.courses().teachers().create(
        courseId=courseId, body=teacher).execute()
    print('Course {0} add Admin User'.format(courseId))


def deleteAdminUser(courseId):
    try:
        serviceEnrollment.courses().teachers().delete(
            courseId=courseId, userId=adminUser).execute()
        print('Course {0} delete Admin User'.format(courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get('error')
        if (error.get('code') == 404):  # 404 is NOT_FOUND
            print('Course Admin Teacher {0} is not found'.format(courseId))
        else:
            raise


def deleteClassroom(courseId):
    try:
        serviceClassroom.courses().delete(id=courseId).execute()
        print('Course {0} has been removed'.format(courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get('error')
        if (error.get('code') == 404):  # 404 is NOT_FOUND
            print('Course ID {0} has already been deleted'.format(courseId))
        else:
            raise
    # serviceClassroom.courses().get(id=courseId).execute()


def enrollStudent(courseId, studentId):
    student = {
        'courseId': courseId,
        'userId': studentId,
        'role': 'STUDENT'
    }
    try:
        student = serviceEnrollment.invitations().create(
            body=student).execute()
        print('done')
    except HttpError as e:
        error = simplejson.loads(e.content).get('error')
        if(error.get('code') == 409):
            print('User {0} are already a member of this course.'.format(
                student['userId']))
        else:
            raise


def enrollStudent3(courseId, studentIds):
    student = []
    for studentId in studentIds:
        student.append({
            'courseId': courseId,
            'userId': studentId,
            'role': 'STUDENT'
        })
    print(student)
    try:
        student = serviceEnrollment.invitations().create(
            body=student).execute()
        print('done')
    except HttpError as e:
        error = simplejson.loads(e.content).get('error')
        if(error.get('code') == 409):
            print('User {0} are already a member of this course.'.format(
                student['userId']))
        else:
            raise


#
# enroll students to a classroom with no confirmation cannot execute
# due to lack of authority for classroom API


def enrollStudent2(courseId, studentId):
    student = {
        'userId': studentId
    }
    try:
        student = serviceEnrollment.courses().students().create(
            courseId=courseId,
            body=student,
            #            enrollmentCode=enrollCode
        ).execute()
        print(
            'User {0} was enrolled as a student in the course with ID "{1}"'
            .format(student.get('profile').get('name').get('fullName'),
                    courseId))
    except HttpError as e:
        error = simplejson.loads(e.content).get('error')
        if(error.get('code') == 409):
            print('User {0} are already a member of this course.'.format(
                student.get('profile').get('name').get('fullName')))
        elif(error.get('code') == 403):
            print('Permission Denied.')
        else:
            print(error.get('code'))
            raise


def listClassroom():
    results = serviceClassroom.courses().list(
        pageSize=0).execute()
#        pageSize=0, courseStates='ACTIVE').execute()
    courses = results.get('courses', [])
    if not courses:
        print('No courses found')
    else:
        print('Courses:')
        with open(options['output_csv'], 'w') as f:
            writer = csv.writer(f, lineterminator='\n')
            # csv indexes
            writer.writerow(
                ['courseName', 'courseSection', 'courseId', 'classCode', 'ownerId', 'teacherName', 'status'])
            for course in tqdm(courses):
                results = serviceEnrollment.courses().teachers().list(
                    courseId=course.get('id')).execute()
                teachers = results.get('teachers', [])
                writer.writerow([course.get('name'), course.get('section'), course.get(
                    'id'), course.get('enrollmentCode'), course.get('ownerId'), teachers[0]['profile']['name']['fullName'], course.get('courseState')])
                # print(u'{0}, {1}, {2}, {3}, {4}, {5}'.format(course.get('name'), course.get('section'), course.get(
                #    'id'), course.get('enrollmentCode'), course.get('ownerId'), teachers[0]['profile']['name']['fullName']))
            # print(teachers[0]['profile']['emailAddress'])
            # for teacher in teachers:
            #    print('teacher: {}'.format(teacher['profile'])) # .get('name').get('fullName')


def infoClassroom(courseId):
    results = serviceClassroom.courses().get(id=courseId).execute()
    print(results)


# main()
courseIdFile = "coursesID.csv"

if __name__ == '__main__':
    global adminUser
    global options
    execMode, options = parseOptions()
    #print(execMode, options)
    # evaluate specified key of dict object
    # if 'enrollFile' in options:
    #    print(options['enrollFile'])
    # exit()
    # load config.ini
    inifile = configparser.ConfigParser()
    inifile.read('./config.ini', 'UTF-8')
    adminUser = inifile.get('user', 'adminUser')
    readData()
    if not options['dry-run']:
        file = open(courseIdFile, 'a')
        csvWrite = csv.writer(file)
    # Google Classroom API activation
    if not options['dry-run']:
        api_init_class()    # for course management
        api_init_enroll()   # for teacher/student management
    if execMode == 'create' or execMode == 'default':
        target = classSubjects
    elif execMode == 'remove':
        for courseId in options['courses']:
            deleteClassroom(courseId)
        exit()
    elif execMode == 'lists':
        listClassroom()
        exit()
    elif execMode == 'info':
        print("course Information..")
        infoClassroom(options['courseId'])
        exit()
    else:
        target = courseLists
    for classCode in target.keys():
        classTeacher = classTeachers[classCode]+"@fuk.kindai.ac.jp"
        classSubject = classSubjects[classCode] + '(' + classCode + ')'
        classSection = classSections[classCode]
        courseId = courseLists[classCode] if courseLists[classCode] else 0
        if execMode == 'create' or execMode == 'default':
            print('creating..')
            print('Course    ID:{}'.format(courseId))
            print('Unipa   Code:{}'.format(classCode))
            print('Course  Name:{}'.format(classSubject))
            print('Subject Name:{}'.format(classSection))
            print('Lecturer    :{}'.format(classTeacher))
            if not option['dry-run']:
                # create Classroom ownered by class teacher.
                courseId, enrollCode = createClassroom(
                    classSubject, classSections[classCode], classTeacher)
                csvWrite.writerow(
                    [classCode, courseId, classSubject, classTeacher, enrollCode])
        # deleteAdminUser(courseLists[classCode])
        # addAdminUser(courseId)
        #
        if execMode == 'enroll' or execMode == 'default':
            print('enrolling..')
            # add adminUser while students are added to a course
            if classCode in enrollStudents:
                if classTeacher != adminUser and not options['dry-run']:
                    addAdminUser(courseId)
                # print(enrollStudents[classCode])
                for studentId in enrollStudents[classCode]:
                    studentEmail = studentEmails[studentId]
                    print(classCode, studentId, end="")
                    if not option['dry-run']:
                        enrollStudent(courseId, studentEmail)
                    # print(studentEmail, end="")
                if classTeacher != adminUser and not options['dry-run']:
                    deleteAdminUser(courseId)
    if not options['dry-run']:
        file.close()
