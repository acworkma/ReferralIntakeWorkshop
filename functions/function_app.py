"""Box 5 of the reference architecture: the orchestration function.

The trigger is what makes this an event-driven pipeline rather than an
application feature. A blob landing in the ``incoming`` container raises an
Event Grid event, Event Grid writes that event to a storage queue, and this
function picks it up. Nothing here knows or cares whether the web app, azcopy,
or a real upstream system put the document there.

The work itself lives in ``referral.intake`` so it can be tested and driven from
the diagnostics CLI without a Functions host.
"""

import logging

import azure.functions as func

from referral.config import settings
from referral.intake import handle_event

app = func.FunctionApp()

logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)


@app.function_name(name="ReferralIntake")
@app.queue_trigger(
    arg_name="message",
    queue_name="%QUEUE_NAME%",
    connection="AzureWebJobsStorage",
)
def referral_intake(message: func.QueueMessage) -> None:
    logging.info(
        "Received a blob event from %s (delivery attempt %s).",
        settings.queue_name,
        message.dequeue_count,
    )
    referral_id = handle_event(message.get_body())
    if referral_id:
        logging.info("Referral %s is in the review queue.", referral_id)
