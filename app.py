from flask import Flask, request, redirect, render_template, url_for, send_file, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
import io
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# ---------- Config ----------
app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb://localhost:27017/grade_app"
mongo = PyMongo(app)

MIN_GRADE = 6
MAX_GRADE = 10
TARGET_AVG = 8.0

# ---------- Helpers ----------
def to_objid(id_str):
    try:
        return ObjectId(id_str)
    except Exception:
        return None

def linear_regression_predict(points):
    """
    points: list of (x_float, grade_float)
    returns predicted grade (clipped MIN_GRADE..MAX_GRADE)
    """
    n = len(points)
    if n == 0:
        return None
    if n == 1:
        return float(points[0][1])

    xs, ys = zip(*points)
    x_mean, y_mean = sum(xs)/n, sum(ys)/n
    num = sum((x - x_mean)*(y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean)**2 for x in xs)
    slope = num/den if den != 0 else 0
    intercept = y_mean - slope*x_mean

    # Predict for next x
    deltas = [xs[i+1]-xs[i] for i in range(n-1)] if n>1 else [1]
    next_x = xs[-1] + sum(deltas)/len(deltas)
    pred = slope*next_x + intercept
    return round(max(MIN_GRADE, min(MAX_GRADE, pred)), 2)

def prepare_points_from_subjects(subjects):
    """Convert subjects into (x, grade) points for regression"""
    pts = []
    for idx, s in enumerate(subjects):
        dt = s.get("date_added")
        x = dt.timestamp() if hasattr(dt, "timestamp") else idx
        grade = float(s.get("grade", 0))
        pts.append((x, grade))
    return pts

# ---------- PREDICTION API ----------
@app.route("/predict/<student_id>")
def predict(student_id):
    subjects = list(mongo.db.subjects.find({"student_id": str(student_id)}).sort("date_added", 1))
    if not subjects:
        return jsonify({"prediction": None, "baseline_avg": None, "explanation": "No grades available."})

    points = prepare_points_from_subjects(subjects)
    pred = linear_regression_predict(points)
    grades = [float(s.get("grade",0)) for s in subjects]
    baseline_avg = round(sum(grades)/len(grades),2) if grades else None

    explanation = "Prediction based on linear trend of historical grades."
    if pred is None:
        pred = baseline_avg
        explanation = "Not enough history; using baseline average."

    return jsonify({"student_id": student_id, "prediction": pred, "baseline_avg": baseline_avg, "explanation": explanation})

# ---------- EXPORT ----------
@app.route("/export/<student_id>/<fmt>")
def export_student(student_id, fmt):
    oid = to_objid(student_id)
    if not oid:
        return "Student not found", 404
    student = mongo.db.students.find_one({"_id": oid})
    if not student:
        return "Student not found", 404

    subjects = list(mongo.db.subjects.find({"student_id": str(student_id)}).sort("date_added", 1))
    rows = []
    for s in subjects:
        dt = s.get("date_added")
        dt_str = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt) if dt else "N/A"
        rows.append({"Subject": s.get("subject",""), "Grade": s.get("grade",""), "Date Added": dt_str})
    df = pd.DataFrame(rows)

    if fmt == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return send_file(io.BytesIO(buf.getvalue().encode("utf-8")), mimetype="text/csv",
                         as_attachment=True, download_name=f"{student.get('name','student')}_subjects.csv")
    elif fmt == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Subjects")
            summary = {"Student":[student.get("name","")],
                       "Average":[round(df["Grade"].mean(),2) if not df.empty else 0],
                       "Subjects count":[len(df)]}
            pd.DataFrame(summary).to_excel(writer, index=False, sheet_name="Summary")
        buf.seek(0)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"{student.get('name','student')}_subjects.xlsx")
    elif fmt == "pdf":
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf)
        styles = getSampleStyleSheet()
        story = [Paragraph(f"Student: <b>{student.get('name','')}</b>", styles['Title']),
                 Paragraph(f"Index: {student.get('index','')}", styles['Normal']),
                 Paragraph(f"City: {student.get('city','')}", styles['Normal']),
                 Spacer(1,12)]
        if df.empty:
            story.append(Paragraph("No subjects available.", styles['Normal']))
        else:
            data = [list(df.columns)] + [list(r) for r in df.values]
            t = Table(data, colWidths=[220,60,150])
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#f2f2f2")),
                                   ('GRID',(0,0),(-1,-1),0.5,colors.grey),
                                   ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
            story.append(t)
        doc.build(story)
        buf.seek(0)
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                         download_name=f"{student.get('name','student')}_subjects.pdf")
    return "Unsupported format", 400

# ---------- HOME ----------
@app.route("/")
def index():
    search = request.args.get("search","").strip()
    query = {"$or":[{"name":{"$regex":search,"$options":"i"}},
                    {"city":{"$regex":search,"$options":"i"}}]} if search else {}

    students = list(mongo.db.students.find(query))
    for s in students:
        subs = list(mongo.db.subjects.find({"student_id": str(s["_id"])}))
        grades = [float(x.get("grade",0)) for x in subs] if subs else []
        s["avg"] = round(sum(grades)/len(grades),2) if grades else 0
        s["subjects_count"] = len(subs)
        s["has_fail"] = any(g<MIN_GRADE for g in grades)

    highest = max(students,key=lambda x:x["avg"],default=None)
    lowest = min(students,key=lambda x:x["avg"],default=None)
    avg_all = round(sum(s["avg"] for s in students)/len(students),2) if students else 0

    return render_template("index.html", students=students,
                           avg_all=avg_all,
                           highest_avg_student=highest if highest else {"name":"-","avg":0},
                           lowest_avg_student=lowest if lowest else {"name":"-","avg":0},
                           search=search)

# ---------- ADD / EDIT / DELETE STUDENT ----------
# app.py - НОВА
@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        name = request.form.get("student_name", "").strip()
        if not name:
            return "Error: Name required!", 400
        mongo.db.students.insert_one({
            "name": name,
            "index": request.form.get("student_index", "").strip(),
            "city": request.form.get("student_city", "").strip()
        })
        return redirect(url_for("index"))

    # Ако барањето е GET, прикажи ја формата
    return render_template(
        "add_student.html")  # или redirect(url_for('index')) ако само ја користите формата во index.html

@app.route("/edit_student/<id>", methods=["POST"])
def edit_student(id):
    oid = to_objid(id)
    if not oid:
        return "Student not found", 404
    new_name = request.form.get("new_name","").strip()
    if not new_name:
        return "Error: Name required!", 400
    mongo.db.students.update_one({"_id":oid},{"$set":{
        "name": new_name,
        "index": request.form.get("new_index","").strip(),
        "city": request.form.get("new_city","").strip()
    }})
    return redirect(url_for("index"))

@app.route("/delete_student/<id>")
def delete_student(id):
    oid = to_objid(id)
    if oid:
        mongo.db.students.delete_one({"_id":oid})
        mongo.db.subjects.delete_many({"student_id": str(id)})
    return redirect(url_for("index"))

# ---------- STUDENT PAGE ----------
@app.route("/student/<id>", methods=["GET","POST"])
def student_page(id):
    oid = to_objid(id)
    if not oid:
        return "Student not found", 404
    student = mongo.db.students.find_one({"_id":oid})
    if not student:
        return "Student not found", 404

    if request.method == "POST":
        subj_name = request.form.get("subject_name","").strip()
        try:
            grade = float(request.form.get("grade",""))
        except:
            return "Error: Invalid grade", 400
        if not subj_name or grade<MIN_GRADE or grade>MAX_GRADE:
            return f"Error: Grade must be {MIN_GRADE}-{MAX_GRADE}", 400
        mongo.db.subjects.insert_one({
            "student_id": str(id),
            "subject": subj_name,
            "grade": grade,
            "date_added": datetime.utcnow()
        })
        return redirect(url_for("student_page", id=id))

    search = request.args.get("search","").strip()
    sort = request.args.get("sort","desc")
    query = {"student_id": str(id)}
    if search:
        query["subject"] = {"$regex":search,"$options":"i"}

    subjects = list(mongo.db.subjects.find(query))
    subjects.sort(key=lambda x:x.get("grade",0), reverse=(sort!="asc"))
    grades = [float(s.get("grade",0)) for s in subjects] if subjects else []
    avg = round(sum(grades)/len(grades),2) if grades else 0.0

    # Calculate required grade for next subject to reach TARGET_AVG
    if grades:
        required = TARGET_AVG*(len(grades)+1)-sum(grades)
        if required>MAX_GRADE:
            required_grade = None
        elif required<MIN_GRADE:
            required_grade = MIN_GRADE
        else:
            required_grade = round(required,2)
    else:
        required_grade = TARGET_AVG

    weak_subjects = [s for s in subjects if float(s.get("grade",0))<7]

    return render_template("student.html",
                           student=student,
                           subjects=subjects,
                           avg=avg,
                           search=search,
                           sort=sort,
                           target_avg=TARGET_AVG,
                           required_grade=required_grade,
                           weak_subjects=weak_subjects)

# ---------- EDIT / DELETE SUBJECT ----------
@app.route("/edit_subject/<student_id>/<subject_id>", methods=["POST"])
def edit_subject(student_id, subject_id):
    oid = to_objid(subject_id)
    if not oid:
        return "Subject not found", 404
    new_name = request.form.get("new_name","").strip()
    try:
        new_grade = float(request.form.get("new_grade",""))
    except:
        return "Error: Invalid grade", 400
    if not new_name or new_grade<MIN_GRADE or new_grade>MAX_GRADE:
        return f"Error: Grade must be {MIN_GRADE}-{MAX_GRADE}", 400
    mongo.db.subjects.update_one({"_id":oid},{"$set":{"subject":new_name,"grade":new_grade}})
    return redirect(url_for("student_page", id=student_id))

@app.route("/delete_subject/<student_id>/<subject_id>")
def delete_subject(student_id, subject_id):
    oid = to_objid(subject_id)
    if oid:
        mongo.db.subjects.delete_one({"_id":oid})
    return redirect(url_for("student_page", id=student_id))

# ---------- Run ----------
if __name__=="__main__":
    app.run(debug=True, port=5001)
