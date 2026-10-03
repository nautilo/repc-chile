from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os, secrets

app=Flask(__name__)
app.config["SECRET_KEY"]=os.environ.get("SECRET_KEY","dev-change-me")
uri=os.environ.get("DATABASE_URL","sqlite:///repc.db")
if uri.startswith("postgres://"): uri=uri.replace("postgres://","postgresql://",1)
app.config["SQLALCHEMY_DATABASE_URI"]=uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
db=SQLAlchemy(app)

class User(db.Model):
 id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(120),nullable=False); email=db.Column(db.String(160),unique=True,nullable=False); password=db.Column(db.String(255),nullable=False); role=db.Column(db.String(30),nullable=True); capabilities=db.Column(db.String(200),nullable=False,default=""); school_id=db.Column(db.Integer,db.ForeignKey("school.id"))
class School(db.Model):
 id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(160),nullable=False); city=db.Column(db.String(100),nullable=False); receives=db.Column(db.Boolean,default=True); repairs=db.Column(db.Boolean,default=False); certifies=db.Column(db.Boolean,default=False)
class Computer(db.Model):
 id=db.Column(db.Integer,primary_key=True); code=db.Column(db.String(30),unique=True,nullable=False); brand=db.Column(db.String(60)); model=db.Column(db.String(100)); cpu=db.Column(db.String(100)); ram=db.Column(db.Integer,default=0); storage=db.Column(db.Integer,default=0); battery=db.Column(db.Integer,default=0); weight=db.Column(db.Float,default=0); status=db.Column(db.String(40),default="DONATED"); school_id=db.Column(db.Integer,db.ForeignKey("school.id")); donor_id=db.Column(db.Integer,db.ForeignKey("user.id")); notes=db.Column(db.Text,default=""); created_at=db.Column(db.DateTime,default=datetime.utcnow); school=db.relationship("School"); donor=db.relationship("User",foreign_keys=[donor_id])
class CustodyEvent(db.Model):
 id=db.Column(db.Integer,primary_key=True); computer_id=db.Column(db.Integer,db.ForeignKey("computer.id"),nullable=False); actor_id=db.Column(db.Integer,db.ForeignKey("user.id")); event=db.Column(db.String(80),nullable=False); detail=db.Column(db.Text,default=""); created_at=db.Column(db.DateTime,default=datetime.utcnow); computer=db.relationship("Computer"); actor=db.relationship("User")
class StudentProfile(db.Model):
 id=db.Column(db.Integer,primary_key=True); code=db.Column(db.String(30),unique=True,nullable=False); school_id=db.Column(db.Integer,db.ForeignKey("school.id"),nullable=False); power=db.Column(db.Integer,default=3); battery=db.Column(db.Integer,default=3); portability=db.Column(db.Integer,default=3); storage_pref=db.Column(db.Integer,default=3); reserved_pc_id=db.Column(db.Integer,db.ForeignKey("computer.id")); school=db.relationship("School"); reserved=db.relationship("Computer")

def current_user():
 uid=session.get("uid")
 if not uid: return None
 try: return db.session.get(User,uid)
 except Exception:
  db.session.rollback()
  session.pop("uid",None)
  return None
@app.context_processor
def ctx(): return {"me":current_user()}
def login_required(f):
 @wraps(f)
 def w(*a,**k):
  if not current_user(): return redirect(url_for("login"))
  return f(*a,**k)
 return w
def event(pc,kind,detail=""): db.session.add(CustodyEvent(computer_id=pc.id,actor_id=current_user().id if current_user() else None,event=kind,detail=detail))
def score(pc,s):
 p=min(5,1+(pc.ram>=8)+(pc.ram>=16)+(pc.storage>=256)+("i7" in (pc.cpu or "").lower())); b=max(1,min(5,round((pc.battery or 0)/20))); port=5 if pc.weight and pc.weight<=1.3 else 4 if pc.weight and pc.weight<=1.6 else 3 if pc.weight and pc.weight<=2 else 2; st=5 if pc.storage>=512 else 4 if pc.storage>=256 else 3 if pc.storage>=128 else 2
 return max(50,100-(abs(p-s.power)+abs(b-s.battery)+abs(port-s.portability)+abs(st-s.storage_pref))*7)

@app.route("/")
def home(): return render_template("home.html",stats={"pcs":Computer.query.count(),"ready":Computer.query.filter_by(status="CERTIFIED").count(),"schools":School.query.count(),"delivered":Computer.query.filter_by(status="DELIVERED").count()})
@app.route("/register",methods=["GET","POST"])
def register():
 if request.method=="POST":
  if User.query.filter_by(email=request.form["email"].lower()).first(): flash("Ese correo ya está registrado."); return redirect(url_for("register"))
  u=User(name=request.form["name"],email=request.form["email"].lower(),password=generate_password_hash(request.form["password"],method="pbkdf2:sha256"),capabilities=",".join(request.form.getlist("capabilities")) or "donor"); db.session.add(u); db.session.commit(); session["uid"]=u.id; return redirect(url_for("dashboard"))
 return render_template("register.html")

@app.route("/school-register",methods=["GET","POST"])
def school_register():
 if request.method=="POST":
  email=request.form.get("email","").strip().lower()
  if User.query.filter_by(email=email).first():
   flash("Ese correo ya está registrado.")
   return redirect(url_for("school_register"))
  s=School(name=request.form["school_name"].strip(),city=request.form["city"].strip(),receives=True,repairs="repairs" in request.form,certifies="certifies" in request.form)
  db.session.add(s); db.session.flush()
  u=User(name=request.form["name"].strip(),email=email,password=generate_password_hash(request.form["password"],method="pbkdf2:sha256"),role="school_coordinator",capabilities="",school_id=s.id)
  db.session.add(u); db.session.commit()
  session.clear(); session["uid"]=u.id
  flash("Colegio inscrito. Esta cuenta quedó como coordinador del establecimiento.")
  return redirect(url_for("dashboard"))
 return render_template("school_register.html")

@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="GET":
  return render_template("login.html")
 if request.method=="POST":
  email=request.form.get("email","").strip().lower()
  password=request.form.get("password","")
  u=User.query.filter_by(email=email).first()
  if u and check_password_hash(u.password,password):
   session.clear()
   session["uid"]=u.id
   return redirect(url_for("dashboard"))
  flash("Credenciales incorrectas.")
 return render_template("login.html")

@app.route("/health")
def health(): return {"ok":True,"database":uri.split(":")[0]}

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("home"))
@app.route("/dashboard")
@login_required
def dashboard(): return render_template("dashboard.html",pcs=Computer.query.order_by(Computer.created_at.desc()).all(),schools=School.query.all())
@app.route("/donate",methods=["GET","POST"])
@login_required
def donate():
 if request.method=="POST":
  pc=Computer(code="CL-"+secrets.token_hex(3).upper(),brand=request.form["brand"],model=request.form["model"],cpu=request.form["cpu"],ram=int(request.form["ram"]),storage=int(request.form["storage"]),battery=int(request.form["battery"]),weight=float(request.form["weight"] or 0),donor_id=current_user().id,notes=request.form["notes"]); db.session.add(pc); db.session.flush(); event(pc,"DONATED","Equipo registrado por donante"); db.session.commit(); flash(f"Equipo {pc.code} registrado."); return redirect(url_for("computer",pcid=pc.id))
 return render_template("donate.html")
@app.route("/pc/<int:pcid>")
def computer(pcid):
 pc=db.get_or_404(Computer,pcid); events=CustodyEvent.query.filter_by(computer_id=pc.id).order_by(CustodyEvent.created_at.desc()).all(); return render_template("computer.html",pc=pc,events=events,schools=School.query.all())
@app.route("/pc/<int:pcid>/action",methods=["POST"])
@login_required
def pc_action(pcid):
 pc=db.get_or_404(Computer,pcid); action=request.form["action"]; school_id=request.form.get("school_id"); mapping={"receive":"RECEIVED","diagnose":"DIAGNOSED","repair":"REPAIRED","certify":"CERTIFIED","deliver":"DELIVERED"}
 if action=="receive" and school_id: pc.school_id=int(school_id)
 if action in mapping: pc.status=mapping[action]; event(pc,mapping[action],request.form.get("detail","")); db.session.commit(); flash("Estado actualizado.")
 return redirect(url_for("computer",pcid=pc.id))
@app.route("/schools",methods=["GET","POST"])
def schools():
 if request.method=="POST":
  s=School(name=request.form["name"],city=request.form["city"],receives=True,repairs="repairs" in request.form,certifies="certifies" in request.form); db.session.add(s); db.session.commit(); flash("Colegio inscrito para revisión."); return redirect(url_for("schools"))
 return render_template("schools.html",schools=School.query.all())
@app.route("/student",methods=["GET","POST"])
def student():
 if request.method=="POST":
  s=StudentProfile.query.filter_by(code=request.form["code"].upper()).first()
  if not s: flash("Código de estudiante no válido."); return redirect(url_for("student"))
  session["student_id"]=s.id; return redirect(url_for("preferences"))
 return render_template("student.html")
@app.route("/preferences",methods=["GET","POST"])
def preferences():
 s=db.session.get(StudentProfile,session.get("student_id"))
 if not s: return redirect(url_for("student"))
 if request.method=="POST": s.power=int(request.form["power"]); s.battery=int(request.form["battery"]); s.portability=int(request.form["portability"]); s.storage_pref=int(request.form["storage"]); db.session.commit(); return redirect(url_for("catalog"))
 return render_template("preferences.html",s=s)
@app.route("/catalog")
def catalog():
 s=db.session.get(StudentProfile,session.get("student_id"))
 if not s: return redirect(url_for("student"))
 pcs=Computer.query.filter_by(status="CERTIFIED").all(); ranked=sorted([(score(p,s),p) for p in pcs],reverse=True,key=lambda x:x[0]); return render_template("catalog.html",ranked=ranked,s=s)
@app.route("/reserve/<int:pcid>",methods=["POST"])
def reserve(pcid):
 s=db.session.get(StudentProfile,session.get("student_id")); pc=db.get_or_404(Computer,pcid)
 if not s or pc.status!="CERTIFIED": abort(400)
 s.reserved_pc_id=pc.id; pc.status="RESERVED"; db.session.add(CustodyEvent(computer_id=pc.id,event="RESERVED",detail=f"Reservado por perfil estudiantil {s.code}")); db.session.commit(); return render_template("reserved.html",pc=pc)

def seed_data():
 db.create_all()
 if School.query.count()==0:
  a=School(name="Escuela Piloto Los Ríos",city="Valdivia",repairs=True,certifies=True); b=School(name="Escuela Rural Demo",city="Máfil"); db.session.add_all([a,b]); db.session.flush(); admin=User(name="Coordinación Demo",email="demo@repc.cl",password=generate_password_hash("demo1234",method="pbkdf2:sha256"),role="admin",capabilities="donor,technician,transporter",school_id=a.id); db.session.add(admin); db.session.flush()
  db.session.add_all([Computer(code="CL-DEMO01",brand="Lenovo",model="ThinkPad T480",cpu="Intel i5-8350U",ram=16,storage=256,battery=82,weight=1.58,status="CERTIFIED",school_id=a.id,donor_id=admin.id),Computer(code="CL-DEMO02",brand="HP",model="EliteBook 830 G6",cpu="Intel i5-8265U",ram=8,storage=256,battery=91,weight=1.33,status="CERTIFIED",school_id=a.id,donor_id=admin.id),Computer(code="CL-DEMO03",brand="Dell",model="Latitude 5490",cpu="Intel i5-8350U",ram=8,storage=512,battery=74,weight=1.60,status="CERTIFIED",school_id=a.id,donor_id=admin.id),StudentProfile(code="7A-DEMO",school_id=a.id)]); db.session.commit()
@app.cli.command("seed")
def seed(): seed_data(); print("Demo listo: demo@repc.cl / demo1234 | alumno: 7A-DEMO")
with app.app_context():
 try:
  db.create_all()
  from sqlalchemy import inspect, text
  cols=[col["name"] for col in inspect(db.engine).get_columns("user")]
  if "capabilities" not in cols:
   db.session.execute(text("ALTER TABLE user ADD COLUMN capabilities VARCHAR(200) NOT NULL DEFAULT ''"))
   db.session.commit()
  seed_data()
 except Exception as exc:
  db.session.rollback()
  app.logger.exception("Database initialization failed: %s",exc)
