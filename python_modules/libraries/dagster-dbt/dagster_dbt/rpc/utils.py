import logging
from collections import defaultdict
from enum import Enum
from typing import Dict, List

from requests import Response
from requests.exceptions import RequestException

from dagster import Failure, MetadataEntry, RetryRequested
from dagster.core.execution.context.compute import SolidExecutionContext


def fmt_rpc_logs(logs: List[Dict]) -> Dict[int, str]:
    d = defaultdict(list)
    for log in logs:
        levelname = log.get("levelname")
        d[getattr(logging, levelname)].append(
            f"{log.get('timestamp')} - {levelname} - {log.get('message')}"
        )

    return {level: "\n".join(logs) for level, logs in d.items()}


def log_rpc(context: SolidExecutionContext, logs: List[Dict]) -> None:
    if len(logs) > 0:
        logs_fmt = fmt_rpc_logs(logs)
        for level, logs_str in logs_fmt.items():
            context.log.log(level=level, msg=logs_str)


class DBTErrors(Enum):
    project_currently_compiling_error = 10010
    runtime_error = 10001
    server_error = -32000
    project_compile_failure_error = 10011
    rpc_process_killed_error = 10009
    rpc_timeout_error = 10008


def raise_for_rpc_error(context: SolidExecutionContext, resp: Response) -> None:
    error = resp.json().get("error")
    if error is not None:
        if error["code"] in [
            DBTErrors.project_currently_compiling_error.value,
            DBTErrors.runtime_error.value,
            DBTErrors.server_error.value,
        ]:
            context.log.warning(error["message"])
            raise RetryRequested(max_retries=5, seconds_to_wait=30)
        elif error["code"] == DBTErrors.project_compile_failure_error.value:
            raise Failure(
                description=error["message"],
                metadata_entries=[
                    MetadataEntry("RPC Error Code", value=str(error["code"])),
                    MetadataEntry("RPC Error Cause", value=error["data"]["cause"]["message"]),
                ],
            )
        elif error["code"] == DBTErrors.rpc_process_killed_error.value:
            raise Failure(
                description=error["message"],
                metadata_entries=[
                    MetadataEntry("RPC Error Code", value=str(error["code"])),
                    MetadataEntry("RPC Signum", value=str(error["data"]["signum"])),
                    MetadataEntry("RPC Error Message", value=error["data"]["message"]),
                ],
            )
        elif error["code"] == DBTErrors.rpc_timeout_error.value:
            raise Failure(
                description=error["message"],
                metadata_entries=[
                    MetadataEntry("RPC Error Code", value=str(error["code"])),
                    MetadataEntry("RPC Timeout", value=str(error["data"]["timeout"])),
                    MetadataEntry("RPC Error Message", value=error["data"]["message"]),
                ],
            )
        else:
            raise Failure(
                description=error["message"],
                metadata_entries=[
                    MetadataEntry("RPC Error Code", value=str(error["code"])),
                ],
            )


def is_fatal_code(e: RequestException) -> bool:
    """Helper function to determine if a Requests reponse status code
    is a "fatal" status code. If it is, we will not request a solid retry."""
    return 400 <= e.response.status_code < 500 and e.response.status_code != 429
