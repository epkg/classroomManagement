Google Classroom Management
===
Google Classroom 内にクラスを作成したりクラスに学生を追加するための Python アプリケーション

G Suite では Google Cloud Platform と呼ばれる基盤の上で動作していて、様々なアプリケーションに対してコマンドライン操作(GAM; Google Apps Manager) やプログラム(GAS; Google App Script や Python, Java ）などから普通はできない作業も含めて実行できてしまいます。

Google Classroom は Google のポリシーもあり、教員（教師）が持つクラスは管理者でさえ GUI 上からは見ることが出来ません。
このため、今回のオンライン授業ブームでどのくらいクラスが作られているのかさえ分かりません。
Google Classroom API を使うことで、これを解決できます。


# Google Classroom API を使うための準備
Google の API を使うためには GCP(Google Cloud Platform)上の 「IAM と管理」を使って API 利用のために Client Key(と Secret Key)を取得した上で OAuth2 によるユーザ認証を噛ませておきました。（詳細は [Google Classroom API Manual(Python)](https://developers.google.com/classroom/quickstart/python) を参照）

IAM から上記の鍵ペアを含む credentials を json 形式でダウンロードし、credentials.json という名前で保存します。

さらに Python3 系の環境下でライブラリを追加します

```
% pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
% pip install --upgrade simplejson docopt tqdm
```

以上を追加した上で

```
% python3 classroomManagement.py --help
```

とすれば以下のようなヘルプが見えるはずです。

使い方：
```
classroomManagement.py

Usage:
    classroomManagement.py all [--dry-run] [--teacher] [--foreign-domain] [--debug]
    classroomManagement.py create [<class_file>] [--dry-run] [--debug]
    classroomManagement.py enroll [<enroll_file>] [--class <class_file>] [--dry-run] [--teacher] [--foreign-domain] [--debug]
    classroomManagement.py remove <courses>... [--dry-run] [--debug]
    classroomManagement.py lists <output_csv> [--debug]
    classroomManagement.py info <course_id> [--debug]
    classroomManagement.py -h | --help

Options:
    all         create new courses and enroll users on the Google Classroom.
    create      create only new courses (default: classes.csv).
    enroll      enroll users on courses (default: enrollments.csv).
                --teacher: invite / enroll Teacher role(default Student role)
                --foreign-domain: force invite mode
    remove      remove courses from classroom(courseId1 courseId2 ... ).
    lists       lists of all courses.
    info        information of course information.

    -h --help   Show this screen and exit.
```

# 各種ファイルの準備
実際のプログラムを実行する流れは以下のとおりです
まず、最初に管理者アカウントを記した config.ini を作成します

- config.ini
```
[user]
adminUser=administrator@ef.gh.com
```

入力は履修登録システム等から出力できる授業一覧(classes.csv) と登録者一覧(enrollments.csv)、さらには学籍番号や教職員番号等とメールアドレスを対応付ける(users.csv) を準備します。

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

-users.csv
```
12345678901,asdf@ef.gh.com
12345678902,abcd@ef.gh.com
```

# 実行手順
全ての教員が学生が同一ドメイン内(例： xxxx@ef.gh.com)でアカウントを保有している場合において、classes.csv にある授業を Classroom 上で作成し、enrollments.csv にしたがって学生を登録する場合、上記ファイルを同じディレクトリにおいた状態で

```
% python3 classroomManagement.py all
```

とすれば作成できます。
なお、プログラムの初回実行時には、３つの権限レベル(Authorize Request)を利用するために OAuth2 が要求され、token情報(token.pickle)がローカルに保存されます。

作成されたコースの一覧は coursesID.csv というファイルに出力されます。
もし、学生が別ドメイン (例： xxxx@ed.ef.gh.com) である場合、

```
% python3 classroomManagement.py all --foreign-domain
```
とすることで、教員が学生を招待することができます（同一ドメイン内であれば「招待」ではなく「登録」が可能です）


**ただし、教員による学生や教員(--teacher オプション)の招待は 500件/日 と制限が掛かるようなので注意が必要です。**
cf. https://support.google.com/edu/classroom/answer/7300976


この他にも授業クラス（コース）だけを作成したい場合は

```
% python3 classroomManagement.py create [<class_file>]
```

として、実行します(class_file は指定がなければ classes.csv を使用)。その後、履修名簿が確定したら

```
% python3 classroomManagement.py enroll [<enroll_file>]
```

として学生を投入します。
なお、enroll および lists 処理については、Multiprocessing による並列実行が可能です。Google Classroom API ではクラス登録・削除は 1 ユーザ毎、開講クラス一覧に各コースの概要を取得するには１コース毎に処理が必要となります。
なお、Multiprocessing による最大並列数(maxProcess)はデフォルトで 10 プロセスとしています。Google Classroom API の利用上限は 25 query / sec とあります。手元の環境下では、1 query 辺り 実測で1.5秒弱程度でした。
[Google Classroom API; Usage Limits](https://developers.google.com/classroom/limits?hl=ja)

他にも、指定したコースIDのクラスを削除する remove コマンド(現在のところ、削除確認がないので注意)、開講している全てのクラスを抽出する lists コマンド、特定のコースIDの情報を表示する info コマンドも使えます。