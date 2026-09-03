import azure.functions as func

from referral.app import app
from referral.processing import process_referral

function_app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
asgi = func.AsgiMiddleware(app)


@function_app.route(route="{*route}", auth_level=func.AuthLevel.ANONYMOUS)
async def referral_http(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    return await asgi.handle_async(req, context)


@function_app.queue_trigger(
    arg_name="message",
    queue_name="referral-jobs",
    connection="AzureWebJobsStorage",
)
def referral_worker(message: func.QueueMessage) -> None:
    process_referral(message.get_body().decode("utf-8"))
