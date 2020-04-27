Google Classroom Management
===
Google Classroom 内にクラスを作成したりクラスに学生を追加するための Python アプリケーション

G Suite では Google Cloud Platform と呼ばれる基盤の上で動作していて、様々なアプリケーションに対してコマンドライン操作(GAM; Google Apps Manager) やプログラム(GAS; Google App Script や Python, Java ）などから普通はできない作業も含めて実行できてしまいます。

Google Classroom は Google のポリシーもあり、教員（教師）が持つクラスは管理者でさえ GUI 上からは見ることが出来ません。
このため、今回のオンライン授業の準備でどのくらいクラスが作られているのかさえ分かりません（酷いですよね）。
そこで、Google Classroom API を使ってプログラム(今回は Python)で色々と操作していく方法を取りました。

Google の API を使うためには GCP(Google Cloud Platform)上の 「IAM と管理」を使って API 利用のために Client Key(と Secret Key)を取得した上で OAuth2 によるユーザ認証を噛ませておきました。（詳細は https://developers.google.com/classroom を参照）

IAM から上記の鍵ペアを含む credentials を json 形式でダウンロードし、credentials.json という名前で保存します。
さらに、初回実行時には、このプログラムが利用する２つの権限レベル(Authorize Request)のための OAuth2 が要求され、認証情報がローカルに保存されます。

使い方：
'''
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
'''


実際のプログラムの流れは以下のとおりです

(1) ドメイン内の教員メールアドレスを所有者(Owner)にして、コース（授業クラス）を作ります。

入力は履修登録システム等から出力できる授業一覧(classes.csv) と登録者一覧(enrollments.csv)、さらには学籍番号とメールアドレスを対応付ける(students.csv)
※ 学籍番号やメールは適当に改変しています。
本当は CSV じゃなくて DB にする方が規模が大きくなっても大丈夫なのですが、デバッグしやすくて簡単なので CSV にしています。

この後、学生を追加するのですが、実は (1) の手順と (2) 以降の手順では権限の Scope が何故か違います。今回はしょうがないので２つの権限 Scope を同時に取得して適当に使い分けてます。

(2) 所有者が管理者権限（私）以外の場合、私をその講義の教員として追加
(3) コースに履修者名簿から取得した学籍番号に対応するメールアドレスを追加（１件ずつ）
(4) 所有者が管理者権限（私）以外の場合、コースから私を削除

と言う手順で授業に学生を付与できます。というつもりでコードを作りました。

が・・・ 今回の場合、履修登録が確定するのは来週以降、でも、非常勤の先生方にはクラスがある状態で講習会を受けてほしいという希望を満たすため、(1) だけ先にやって、残りは後まわしになりました。
しょうがないので、coursesID.csv というファイルを新設して、新しく Classroom を作成した際のコースIDと履修登録システムにおける授業コードを対応させた CSV を吐き出すようにしています。
(2) 以降の作業はこの CSV を使って実行していく予定です。
