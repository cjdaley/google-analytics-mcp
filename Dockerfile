FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --upgrade pip setuptools wheel
RUN pip install -e .

# Create a startup script that writes credentials from env var
RUN echo '#!/bin/bash\n\
if [ ! -z "$GOOGLE_SERVICE_ACCOUNT_JSON" ]; then\n\
  echo "$GOOGLE_SERVICE_ACCOUNT_JSON" > /app/service-account.json\n\
fi\n\
python bridge.py' > /entrypoint.sh && chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
