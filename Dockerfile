FROM nexus.zhaw.ch:5000/zhaw/ubuntu24-base
ENV REFRESHED=2026-08-10

RUN apt-get update && apt-get install -y python3 python3-pip python3-venv

WORKDIR /deployment
COPY . /deployment

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/deployment

RUN pip install --no-cache-dir -r requirements.txt

RUN cp /deployment/app/config/settings.example.py /deployment/app/config/settings.py

EXPOSE 80

CMD ["gunicorn", "main:app", \
     "--bind", "0.0.0.0:80", \
     "--workers", "2", \ 
     "--threads", "2", \ 
     "--timeout", "60", \ 
     "--graceful-timeout", "30", \ 
     "--keep-alive", "5", \ 
     "--access-logfile", "-", \ 
     "--error-logfile", "-"]