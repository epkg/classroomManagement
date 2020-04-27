Google Classroom Management
===
Google Classroom 内にクラスを作成したりクラスに学生を追加するための Python アプリケーション

G Suite では Google Cloud Platform と呼ばれる基盤の上で動作していて、様々なアプリケーションに対してコマンドライン操作(GAM; Google Apps Manager) やプログラム(GAS; Google App Script や Python, Java ）などから普通はできない作業も含めて実行できてしまいます。

Google Classroom は Google のポリシーもあり、教員（教師）が持つクラスは管理者でさえ GUI 上からは見ることが出来ません。
このため、今回のオンライン授業の準備でどのくらいクラスが作られているのかさえ分かりません。
そこで、Google Classroom API を使ってプログラム(今回は Python)で色々と操作していく方法を取りました。

Google の API を使うためには GCP(Google Cloud Platform)上の 「IAM と管理」を使って API 利用のために Client Key(と Secret Key)を取得した上で OAuth2 によるユーザ認証を噛ませておきました。（詳細は https://developers.google.com/classroom/quickstart/python を参照）

IAM から上記の鍵ペアを含む credentials を json 形式でダウンロードし、credentials.json という名前で保存します。
さらに、初回実行時には、このプログラムが利用する２つの権限レベル(Authorize Request)のための OAuth2 が要求され、token情報(token.create_class.pickle / token.enroll.pickle)がローカルに保存されます。

さらに Python3 系の環境下でライブラリを追加します

```
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
pip install --upgrade simplejson docopt tqdm
```

以上を追加した上で

```
% python3 classroomCreate.py --help
```

とすれば以下のようなヘルプが見えるはずです。

使い方：
```
Usage:
    createCourse.py all [--dry-run]
    createCourse.py create [<class_file>] [--dry-run]
    createCourse.py enroll [<enroll_file>] [--dry-run]
    createCourse.py remove <courses>... [--dry-run]
    createCourse.py lists <output_csv>
    createCourse.py info <course_id>
    createCourse.py -h | --help

Options:
    all         create new courses and enroll students on the Google Classroom.
    create      create only new courses (default: classes.csv).
    enroll      enroll students on courses (default: enrollments.csv).
    remove      remove courses from classroom(courseId1 courseId2 ... ).
    lists       lists of all courses.
    info        information of course information.

    -h --help   Show this screen and exit.
```


実際のプログラムを実行する流れは以下のとおりです
まず、最初に管理者アカウントを記した config.ini を作成します

- config.ini
```
[user]
adminUser=administrator@ef.gh.com
```

入力は履修登録システム等から出力できる授業一覧(classes.csv) と登録者一覧(enrollments.csv)、さらには学籍番号とメールアドレスを対応付ける(students.csv) を準備します。

以下、各 csv のサンプルです

- classes.csv
```
# 授業コード, 授業名, 教員ID, 授業補足, 教員名
00000A000,卒業研究,1234567,(電気)(○○クラス), ○○ △△
```

-enrollments.csv
```
# 授業コード, 学籍番号
0000A000,12345678901
0000A000,12345678902
```

-students.csv
```
12345678901,asdf@ef.gh.com
12345678902,abcd@ef.gh.com
```

classes.csv にある授業を Classroom 上で作成し、enrollments.csv にしたがって学生を登録する場合、上記ファイルを同一ディレクトリにおいた状態で

```
% python3 classroomCreate.py all
```

とすれば作成できます。作成されたコースの一覧は coursesID.csv というファイルに出力されます。

この他にも授業クラス（コース）だけを作成したい場合は

```
% python3 classroomCreate.py create [<class_file>]
```

として、実行します(class_file は指定がなければ classes.csv を使用)。その後、履修名簿が確定したら

```
% python3 classroomCreate.py enroll [<enroll_file>]
```

として学生を投入します。ただし、現状、一人ずつ学生を追加する必要があるため、大量実行する場合、相当な時間(一人追加するのに約1秒程度)が掛かってしまいます。良い方法があれば・・

他にも、開講している全てのクラスを抽出する lists コマンド、特定のコースIDの情報を表示する info コマンド（こちらは仮実装）も使えます。