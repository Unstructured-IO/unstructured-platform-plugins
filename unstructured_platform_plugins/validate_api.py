from urllib.parse import urljoin

import click
from pydantic import HttpUrl
from requests import Session

from unstructured_platform_plugins.schema.model import is_valid_input_dict


class ApiSession(Session):
    def __init__(self, base_url: HttpUrl = None):
        super().__init__()
        self.base_url = str(base_url)

    def request(self, method, url, *args, **kwargs):
        joined_url = urljoin(self.base_url, url)
        return super().request(method, joined_url, *args, **kwargs)

    def get_url(self, url: str) -> str:
        return urljoin(self.base_url, url)


class ValidationError(Exception):
    pass


def check_endpoint_exists(api_session: ApiSession, endpoint: str):
    try:
        api_session.head(endpoint)
    except Exception as e:
        raise ValidationError(
            f"failed to validate that url exists: {api_session.get_url(url=endpoint)}"
        ) from e


def check_schema_response(api_session: ApiSession):
    resp = api_session.get("/schema")
    try:
        resp.raise_for_status()
    except Exception as e:
        raise ValidationError(
            "failed to validate response from schema "
            "endpoint {}: {}".format(api_session.get_url(url="/schema"), e)
        ) from e
    contents = resp.json()
    if not is_valid_input_dict(contents):
        raise ValidationError("schema response don't conform to expected format")


def check_id_response(api_session: ApiSession):
    resp = api_session.get("/id")
    try:
        resp.raise_for_status()
        contents = resp.text
        assert contents.strip() != ""
    except Exception as e:
        raise ValidationError(
            "failed to validate response from id endpoint "
            "{}: {}".format(api_session.get_url(url="/id"), e)
        ) from e


def create_report(api_session: ApiSession) -> dict[str, str]:
    report = {}
    try:
        check_endpoint_exists(api_session=api_session, endpoint="/invoke")
    except ValidationError as e:
        report["/invoke endpoint existence"] = str(e)

    try:
        check_endpoint_exists(api_session=api_session, endpoint="/schema")

        try:
            check_schema_response(api_session=api_session)
        except ValidationError as e:
            report["/schema endpoint response"] = str(e)

    except ValidationError as e:
        report["/schema endpoint existence"] = str(e)

    try:
        check_endpoint_exists(api_session=api_session, endpoint="/id")

        try:
            check_id_response(api_session=api_session)
        except ValidationError as e:
            report["/id endpoint response"] = str(e)
    except ValidationError as e:
        report["/id endpoint existence"] = str(e)

    return report


@click.command()
@click.option("--api-url", type=HttpUrl, required=True, help="API URL to run validation against")
def validate_api(api_url: HttpUrl) -> None:
    api_session = ApiSession(base_url=api_url)
    report = create_report(api_session=api_session)
    if report:
        print("Api validation failed:")
        for k, v in report.items():
            print(f"{k}: {v}")

        exit(1)
    print("Api validation successful")
    exit(0)


if __name__ == "__main__":
    validate_api()
