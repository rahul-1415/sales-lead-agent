FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

COPY agent ./agent
COPY tools ./tools
COPY api.py config.py db.py storage.py sqs.py lambda_handler.py ./

CMD ["lambda_handler.api_handler"]
