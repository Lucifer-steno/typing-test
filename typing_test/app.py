from flask import Flask,render_template,request,redirect,session
import sqlite3,datetime

app=Flask(__name__)
app.secret_key="typing_secret"


def db():
    return sqlite3.connect("database.db")


# ---------------------------
# SPEED CALCULATION FUNCTION
# ---------------------------

import re
import unicodedata
import difflib


def normalize_text(text):
    text = unicodedata.normalize("NFC", text)
    text = text.replace('\u200c', '').replace('\u200d', '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def split_words(text):
    text = normalize_text(text)
    return text.split()


def calc(original, typed, minutes, mode):

    original_words = split_words(original)
    typed_words = split_words(typed)

    total_words = len(original_words)
    typed_count = len(typed_words)

    correct = 0
    errors = 0

    matcher = difflib.SequenceMatcher(None, original_words, typed_words)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == 'equal':
            for k in range(i2 - i1):
                ow = original_words[i1 + k]
                tw = typed_words[j1 + k]

                if ow == tw:
                    correct += 1
                else:
                    errors += 1

        elif tag == 'replace':
            errors += max(i2 - i1, j2 - j1)

        elif tag == 'delete':
            errors += (i2 - i1)

        elif tag == 'insert':
            errors += (j2 - j1)

    if minutes <= 0:
        minutes = 0.1

    if mode == "word":
        gross_speed = typed_count / minutes
        net_speed = correct / minutes
    else:
        characters = len(typed.strip())
        gross_speed = (characters / 5) / minutes
        net_speed = max(((characters / 5) - errors), 0) / minutes

    accuracy = (correct / total_words) * 100 if total_words > 0 else 0

    return round(gross_speed, 2), round(net_speed, 2), errors, round(accuracy, 2)

@app.route("/add_passage",methods=["GET","POST"])
def add_passage():

    if "admin" not in session:
        return redirect("/admin")

    if request.method == "POST":

        lang = request.form["lang"]
        mode = request.form["mode"]
        content = request.form["content"]

        con = db()
        cur = con.cursor()

        cur.execute(
        "INSERT INTO passages(language,content,mode,active) VALUES(?,?,?,?)",
        (lang,content,mode,0)
        )

        con.commit()
        con.close()

        return redirect("/dashboard")

    return render_template("add_passage.html")


# ---------------------------
# LOGIN
# ---------------------------

@app.route("/",methods=["GET","POST"])
def login():

    if request.method=="POST":

        reg=request.form["reg"]
        dob=request.form["dob"]

        con=db()
        cur=con.cursor()

        cur.execute("SELECT * FROM users WHERE reg=?",(reg,))
        user=cur.fetchone()

        con.close()

        if user and user[2]==dob:

            session.clear()   # 🔥 BEST FIX
            
            session["user"]=reg
            session["name"]=user[1]

            return redirect("/profile")

    return render_template("login.html")


# ---------------------------
# PROFILE CONFIRM
# ---------------------------

@app.route("/profile",methods=["GET","POST"])
def profile():

    if "user" not in session:
        return redirect("/")

    con=db()
    cur=con.cursor()

    cur.execute("SELECT * FROM users WHERE reg=?",(session["user"],))
    student=cur.fetchone()

    con.close()

    if request.method=="POST":
        return redirect("/instructions")

    return render_template("profile.html",student=student)


# ---------------------------
# INSTRUCTIONS
# ---------------------------

@app.route("/instructions",methods=["GET","POST"])
def instructions():

    if request.method=="POST":

        if session.get("eng_done") == True:
            return redirect("/hindi")
        else:
            return redirect("/english")

    return render_template("instructions.html")


# ---------------------------
# ENGLISH TEST
# ---------------------------

import sqlite3, datetime, time

@app.route("/english",methods=["GET","POST"])
def english():

    con=db()
    cur=con.cursor()

    cur.execute("SELECT duration,highlight FROM settings")
    row = cur.fetchone()

    duration = row[0] if row else 10
    highlight = row[1] if row else 1

    cur.execute("""
    SELECT content,mode FROM passages
    WHERE language='ENGLISH' AND active=1
    ORDER BY id DESC
    LIMIT 1
    """)

    row = cur.fetchone()

    passage = row[0] if row else ""
    mode = row[1] if row else "word"

    con.close()

    # ✅ START TIME (जब page खुले)
    if request.method == "GET":
        session["start_time"] = time.time()

    # ✅ SUBMIT
    if request.method=="POST":

        typed = request.form.get("typed","")

        end_time = time.time()
        start_time = session.get("start_time", end_time)

        time_taken = (end_time - start_time) / 60

        if time_taken <= 0:
            time_taken = 0.1

        gross,net,err,acc = calc(passage,typed,time_taken,mode)

        session["eng_wpm"] = net
        session["eng_accuracy"] = acc
        session["errors"] = err
        session["eng_done"]=True

        return redirect("/hindi_instructions")

    return render_template(
        "english_test.html",
        passage=passage,
        duration=duration,
        highlight=highlight
    )


# ---------------------------
# HINDI TEST
# ---------------------------

import sqlite3, datetime, time

@app.route("/hindi",methods=["GET","POST"])
def hindi():

    con = db()
    cur = con.cursor()

    cur.execute("SELECT duration,highlight FROM settings")
    row = cur.fetchone()

    duration = row[0] if row else 10
    highlight = row[1] if row else 1

    cur.execute("""
    SELECT content,mode FROM passages
    WHERE language='HINDI' AND active=1
    ORDER BY id DESC
    LIMIT 1
    """)

    row = cur.fetchone()

    passage = row[0] if row else ""
    mode = row[1] if row else "word"

    con.close()

    # ✅ START TIME (only once)
    if request.method == "GET":
        session["start_time"] = time.time()

    # ✅ SUBMIT
    if request.method == "POST":

        typed = request.form.get("typed","")

        end_time = time.time()
        start_time = session.get("start_time", end_time)

        time_taken = (end_time - start_time) / 60

        if time_taken <= 0:
            time_taken = 0.1

        gross, net, err2, acc = calc(passage, typed, time_taken, mode)

        hin_accuracy = acc
        total_err = session.get("errors", 0) + err2

        con = db()
        cur = con.cursor()

        cur.execute("""
        INSERT INTO results
        (reg,eng_wpm,hin_wpm,errors,date,eng_accuracy,hin_accuracy)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            session["user"],
            session["eng_wpm"],
            net,
            total_err,
            str(datetime.date.today()),
            session["eng_accuracy"],
            hin_accuracy
        ))

        con.commit()
        con.close()

        # ✅ CLEAN SESSION
        session.pop("start_time", None)
        session.pop("eng_done", None)

        return redirect("/thanks")

    return render_template(
        "hindi_test.html",
        passage=passage,
        duration=duration,
        highlight=highlight
    )

@app.route("/hindi_instructions",methods=["GET","POST"])
def hindi_instructions():

    if request.method=="POST":
        return redirect("/hindi")

    return render_template("hindi_instructions.html")


# ---------------------------
# THANK YOU
# ---------------------------

@app.route("/thanks")
def thanks():
    return render_template("thanks.html")


# ---------------------------
# ADMIN LOGIN
# ---------------------------

@app.route("/admin",methods=["GET","POST"])
def admin():

    if request.method=="POST":

        if request.form["u"]=="admin" and request.form["p"]=="1234":
            session["admin"]=True
            return redirect("/dashboard")

    return render_template("admin_login.html")


# ---------------------------
# ADMIN DASHBOARD
# ---------------------------

@app.route("/dashboard",methods=["GET","POST"])
def dashboard():

    if "admin" not in session:
        return redirect("/admin")

    selected_date = str(datetime.date.today())

    if request.method == "POST":
        selected_date = request.form["date"]

    con = db()
    cur = con.cursor()

    # English leaderboard
    cur.execute("""
    SELECT reg,eng_wpm,eng_accuracy
    FROM results
    WHERE date=?
    ORDER BY eng_wpm DESC
    """,(selected_date,))

    eng = cur.fetchall()

    # Hindi leaderboard
    cur.execute("""
    SELECT reg,hin_wpm,hin_accuracy
    FROM results
    WHERE date=?
    ORDER BY hin_wpm DESC
    """,(selected_date,))

    hin = cur.fetchall()

    con.close()

    return render_template(
        "admin_dashboard.html",
        eng=eng,
        hin=hin,
        date=selected_date
    )
    
# ---------------------------
# ACTIVATE PARAGRAPH
# ---------------------------

@app.route("/activate_para/<pid>")
def activate_para(pid):

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    # पहले उसी language के सारे paragraphs inactive
    cur.execute("""
    UPDATE passages
    SET active=0
    WHERE language=(SELECT language FROM passages WHERE id=?)
    """,(pid,))

    # selected paragraph active
    cur.execute("UPDATE passages SET active=1 WHERE id=?",(pid,))

    con.commit()
    con.close()

    return redirect("/paragraphs")

@app.route("/delete_para/<pid>")
def delete_para(pid):

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    cur.execute("DELETE FROM passages WHERE id=?", (pid,))

    con.commit()
    con.close()

    return redirect("/paragraphs")

@app.route("/edit_para/<pid>",methods=["GET","POST"])
def edit_para(pid):

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    if request.method=="POST":

        lang=request.form["lang"]
        mode=request.form["mode"]
        content=request.form["content"]

        cur.execute("""
        UPDATE passages
        SET language=?,content=?,mode=?
        WHERE id=?
        """,(lang,content,mode,pid))

        con.commit()
        con.close()

        return redirect("/paragraphs")

    cur.execute("SELECT * FROM passages WHERE id=?", (pid,))
    para=cur.fetchone()

    con.close()

    return render_template("edit_para.html",para=para)
# ---------------------------
# ENGLISH LEADERBOARD
# ---------------------------

@app.route("/leaderboard_eng", methods=["GET","POST"])
def leaderboard_eng():

    if "admin" not in session:
        return redirect("/admin")

    selected_date = str(datetime.date.today())

    if request.method == "POST":
        selected_date = request.form.get("date")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT reg,eng_wpm,eng_accuracy,date
    FROM results
    WHERE date=?
    ORDER BY eng_wpm DESC
    """,(selected_date,))

    res = cur.fetchall()

    con.close()

    return render_template(
        "leaderboard_eng.html",
        res=res,
        date=selected_date
    )

@app.route("/leaderboard_hin", methods=["GET","POST"])
def leaderboard_hin():

    if "admin" not in session:
        return redirect("/admin")

    selected_date = str(datetime.date.today())

    if request.method == "POST":
        selected_date = request.form.get("date")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT reg,hin_wpm,hin_accuracy,date
    FROM results
    WHERE date=?
    ORDER BY hin_wpm DESC
    """,(selected_date,))

    res = cur.fetchall()

    con.close()

    return render_template(
        "leaderboard_hin.html",
        res=res,
        date=selected_date
    )
# ---------------------------
# ADD STUDENT
# ---------------------------

@app.route("/add_student",methods=["GET","POST"])
def add_student():

    if "admin" not in session:
        return redirect("/admin")

    if request.method=="POST":

        reg=request.form["reg"]
        name=request.form["name"]
        dob=request.form["dob"]

        con=db()
        cur=con.cursor()

        cur.execute("INSERT INTO users VALUES(?,?,?)",(reg,name,dob))

        con.commit()
        con.close()

        return redirect("/students")

    return render_template("add_student.html")
# ---------------------------
# EDIT STUDENT
# ---------------------------

@app.route("/edit_student/<reg>",methods=["GET","POST"])
def edit_student(reg):

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    if request.method=="POST":

        name=request.form["name"]
        dob=request.form["dob"]

        cur.execute(
        "UPDATE users SET name=?,dob=? WHERE reg=?",
        (name,dob,reg)
        )

        con.commit()
        con.close()

        return redirect("/students")

    cur.execute("SELECT * FROM users WHERE reg=?",(reg,))
    student=cur.fetchone()

    con.close()

    return render_template("edit_student.html",student=student)


# ---------------------------
# DELETE STUDENT
# ---------------------------

@app.route("/delete_student/<reg>")
def delete_student(reg):

    con=db()
    cur=con.cursor()

    cur.execute("DELETE FROM users WHERE reg=?",(reg,))

    con.commit()
    con.close()

    return redirect("/students")
# ---------------------------
# STUDENTS PAGE
# ---------------------------

@app.route("/students")
def students():

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    cur.execute("SELECT * FROM users")
    students=cur.fetchall()

    con.close()

    return render_template("students.html",students=students)


# ---------------------------
# PARAGRAPHS PAGE
# ---------------------------

@app.route("/paragraphs")
def paragraphs():

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    cur.execute("SELECT * FROM passages")
    paras=cur.fetchall()

    con.close()

    return render_template("paragraphs.html",paras=paras)


# ---------------------------
# SETTINGS PAGE
# ---------------------------

@app.route("/settings",methods=["GET","POST"])
def settings():

    if "admin" not in session:
        return redirect("/admin")

    con=db()
    cur=con.cursor()

    if request.method=="POST":

        duration=request.form["duration"]
        mode=request.form["mode"]
        highlight = 1 if request.form.get("highlight") else 0

        cur.execute(
        "UPDATE settings SET duration=?,mode=?,highlight=?",
        (duration,mode,highlight)
        )

        con.commit()

    cur.execute("SELECT * FROM settings")
    s=cur.fetchone()

    con.close()

    return render_template("settings.html",s=s)



# ---------------------------
# RUN SERVER
# ---------------------------

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)
