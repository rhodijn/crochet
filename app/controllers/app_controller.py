from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from app.config.settings import Settings
from app.core.middleware.auth_middleware import auth, guest
from app.entities.auth.user_entity import UserEntity
from app.enums.auth.user_role import UserRole
from app.services.auth_service import AuthService
from app.core.translation.i18n import t
from app.services.flash_service import FlashService

app_controller: Blueprint = Blueprint("app_controller", __name__)
config: Settings = Settings()
auth_service: AuthService = AuthService()
flash_service: FlashService = FlashService()

type TemplateResponse = str | tuple[str, int]


@app_controller.route("/login", methods=["GET", "POST"])
@guest
def login() -> Response | TemplateResponse:
    if request.method == "POST":
        username: str = request.form.get("username", "").strip()
        password: str = request.form.get("password", "")

        if not username or not password:
            flash_service.set("error", t("form.login.error"))
            return render_template("pages/auth/login.html"), 400

        user_entity: UserEntity | None = auth_service.authenticate(
            username,
            password,
        ) or auth_service.authenticate_local(
            username,
            password,
        )

        if user_entity is None:
            flash_service.set("error", t("form.login.error"))
            return render_template("pages/auth/login.html"), 401

        role: UserRole = (
            UserRole.ADMIN if user_entity.email in config.LDAP_ADMINS else UserRole.USER
        )

        session.clear()
        session.permanent = False
        session["user_id"] = user_entity.email
        session["user_name"] = user_entity.user_name
        session["first_name"] = user_entity.first_name
        session["last_name"] = user_entity.last_name
        session["display_name"] = user_entity.display_name
        session["email"] = user_entity.email
        session["role"] = role.value

        return redirect(url_for("app_controller.dashboard"))

    return render_template("pages/auth/login.html")


@app_controller.get("/logout")
@auth
def logout() -> Response:
    session.clear()
    return redirect("/login")


@app_controller.get("/")
@auth
def dashboard() -> str:
    return render_template("pages/home/index.html")
