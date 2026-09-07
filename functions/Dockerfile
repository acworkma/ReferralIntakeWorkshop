# The Function App runs with public network access disabled, which also turns
# off the SCM/Kudu endpoint that zip deployment pushes to. A custom container is
# the way in: the app pulls this image from the registry over its own private
# endpoint, so nothing has to reach inbound.
#
# Build from the repository root so the shared `referral` package is in context:
#   az acr build -r <registry> -t referral-func:<tag> -f functions/Dockerfile .
FROM mcr.microsoft.com/azure-functions/python:4-python3.12

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCEPT_EULA=Y

# pyodbc needs the Microsoft ODBC driver to reach Azure SQL over the private endpoint.
# The Functions base image already registers packages.microsoft.com, so the driver
# only has to be installed. Re-adding the repository breaks the build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends unixodbc msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

COPY functions/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY functions/host.json functions/function_app.py /home/site/wwwroot/
# The pipeline logic is shared with the API rather than duplicated, so both
# surfaces apply identical validation and extraction to the same document.
COPY api/referral/ /home/site/wwwroot/referral/
