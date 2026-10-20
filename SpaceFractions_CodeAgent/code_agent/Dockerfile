# Headless CLI image (the GUI is Windows-only). Usage:
#   docker build -t codeagent .
#   docker run --rm -e DEEPSEEK_API_KEY=... -v %cd%/in:/in -v %cd%/out:/out codeagent \
#     --doc /in/Architecture_Documentation.md --views /in/Architecture_View.md --out /out
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir requests
COPY codeagent ./codeagent
ENTRYPOINT ["python", "-m", "codeagent"]
