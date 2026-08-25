from flask import Flask, render_template, request, redirect, session, jsonify  # 1. 加上 session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List
from werkzeug.security import generate_password_hash, check_password_hash
from modelscope import AutoModelForCausalLM, AutoTokenizer
import torch


app = Flask(__name__)

# 2. 加上 secret_key，这是 Session 必须的“加密钥匙”
app.secret_key = "login-true"
app.config['SESSION_PERMANENT'] = False

# 数据库配置
HOSTNAME = "127.0.0.1"
PORT = "3306"
USERNAME = "root"
PASSWORD = "1qaz2wsx3edc"
DATABASE = "nexus"

app.config['SQLALCHEMY_DATABASE_URI'] = \
    f"mysql+mysqldb://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DATABASE}?charset=utf8mb4"

db = SQLAlchemy(app)

print("正在启动 AI 引擎...")
model_path = "qwen/Qwen2-1.5B-Instruct" # ModelScope 会自动识别这个路径并从国内服务器下载
import os
os.environ["MODELSCOPE_CACHE"] = "D:/AI_Models"

# 注意：ModelScope 的 AutoTokenizer 和 AutoModelForCausalLM 用法和 transformers 几乎一样
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map="auto",      # 自动分配显卡/CPU
    torch_dtype=torch.float16, # 使用半精度，省显存
    trust_remote_code=True
)
model.eval()
print("AI 引擎启动完毕！")

class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    username: Mapped[str] = mapped_column(db.String(50), nullable=False)
    password: Mapped[str] = mapped_column(db.String(200), nullable=False)

    department_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    Department: Mapped["Department"] = relationship("Department", back_populates="users")


class Department(db.Model):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(50), nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="Department")


def init_db():
    existing_root = User.query.filter_by(username="root").first()

    if not existing_root:
        hashed_pw = generate_password_hash("1q2w3e1a2s3d1z2x3c")
        root = User(username="root", password=hashed_pw)
        db.session.add(root)
        db.session.commit()

def del_user(user_id):
    user = User.query.get(user_id)
    db.session.delete(user)
    db.session.commit()

with app.app_context():
    db.create_all()
    init_db()

# 3. 首页加上 Session 判断，看看有没有人登录
@app.route("/")
def index():
    user_id = session.get('user_id')
    if user_id:
        current_user = User.query.get(user_id)
        return render_template("index.html", user=current_user)
    return render_template("index.html", user=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    elif request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            # 4. 登录成功，发“手环”！把用户ID存进 Session
            session['user_id'] = user.id
            return redirect(f"/user/{user.id}")
        else:
            return render_template("error-login.html")


@app.route("/reg", methods=["GET", "POST"])
def reg():
    if request.method == "GET":
        return render_template("register.html", departments=Department.query.all())

    elif request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        dept_id_str = request.form.get("department_id")

        department_id = int(dept_id_str)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template("error1-register.html")

        existing_department = Department.query.get(department_id)
        if not existing_department:
            return render_template("error2-register.html")

        user = User(username=username, password=password, department_id=department_id)
        db.session.add(user)

        db.session.commit()

        return redirect("/")


@app.route("/user/<int:id>")
def user(id):
    # 1. 获取当前登录用户的 ID
    current_user_id = session.get('user_id')

    # 2. 判断：如果访问的 id 和当前登录的 id 不一致，直接拦截！
    if current_user_id != id:
        return 403

    # 3. 如果一致，才去查询数据库并返回页面
    user = User.query.get(id)
    return render_template("user.html", user=user)


@app.route("/pud", methods=["GET", "POST"])
def pud():
    if request.method == "GET":
        return render_template("pud.html")
    elif request.method == "POST":
        root_pw = request.form["root_password"]
        department_name = request.form["department_name"]

        stored_password_hash = User.query.get(1).password
        if check_password_hash(stored_password_hash, root_pw):
            department = Department(name=department_name)
            db.session.add(department)
            db.session.commit()
            return redirect("/")
        else:
            return render_template("error1-pud.html")


@app.route("/logout",methods=["GET", "POST"])
def logout():
    if request.method == "GET":
        return render_template("logout.html")
    elif request.method == "POST":
        session.pop('user_id', None)
        return redirect("/login")

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/delete_user", methods=["POST"])
def delete_user_route():
    user_id = request.form.get("user_id")
    if user_id:
        del_user(int(user_id))

    return redirect("/user/root/manage")

@app.route("/user/root/manage")
def root_manage():
    users = User.query.all()
    return render_template("manage.html", users=users)

@app.route("/api/ai", methods=["POST"])
def api_ai():
    # 从请求的 JSON 数据中获取 'text'
    data = request.get_json()
    user_input = data.get('text')

    if not user_input:
        return jsonify({"error": "请求中缺少 'text' 字段"}), 400

    # --- AI 模型处理逻辑 ---
    messages = [
        {"role": "system", "content": "你是一个有用的助手。"},
        {"role": "user", "content": user_input}
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([text], return_tensors="pt").to(model.device)

    outputs = model.generate(**inputs, max_new_tokens=512)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    ret = response.split("<|im_start|>assistant\n")[-1]

    return jsonify({"response": ret})

@app.route("/ai")
def ai_page():
    return render_template("ai.html")

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404
@app.errorhandler(403)
def page_forbidden(error):
    return render_template("403.html"), 403
@app.errorhandler(500)
def page_server_error(error):
    return render_template("500.html"), 500
@app.errorhandler(502)
def page_not_found(error):
    return render_template("502.html"), 502
@app.errorhandler(504)
def page_forbidden(error):
    return render_template("504.html"), 504
@app.errorhandler(400)
def page_not_found(error):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0", port=5000)