#!/usr/bin/env python3

import logging

import requests
from flask import Blueprint, redirect, render_template, request, url_for

from app.config.settings import Settings
from app.services.flash_service import FlashService
from app.services.object_service import search_objects

app_controller: Blueprint = Blueprint("app_controller", __name__)
config: Settings = Settings()
flash_service: FlashService = FlashService()
logger = logging.getLogger(__name__)


@app_controller.get("/")
def dashboard() -> str:
    return render_template("pages/home/index.html")


@app_controller.get("/explore")
def explore() -> str:
    q = request.args.get("q", "").strip()
    objects: list[dict] = []
    error = False
    if q:
        try:
            objects = search_objects(q)
        except requests.RequestException:
            logger.exception("SKKG search failed")
            error = True
    return render_template(
        "pages/explore/explore.html", objects=objects, q=q, error=error
    )


@app_controller.get("/explore_sub")
def explore_sub():
    # The card link sends ?id=...&title=...&description=...
    title = request.args.get("title", "").strip()
    if not title:
        return redirect(url_for("app_controller.explore"))
    obj = {
        "id": request.args.get("id", ""),
        "title": title,
        "description": request.args.get("description", ""),
    }
    return render_template("pages/explore/explore_sub.html", obj=obj)


@app_controller.get("/about")
def about() -> str:
    return render_template("pages/about/about.html")