"""In-memory fakes of the external services, reused by pipeline and API tests."""

from app.pipeline import Pipeline


class FakeHeadlines:
    def __init__(self, headline: str = "Test Headline") -> None:
        self.headline = headline
        self.error: Exception | None = None

    def fetch_top_headline(self) -> str:
        if self.error:
            raise self.error
        return self.headline


class FakeImages:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.error: Exception | None = None

    def generate(self, prompt: str) -> bytes:
        if self.error:
            raise self.error
        self.prompts.append(prompt)
        return f"image-{len(self.prompts)}".encode()


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.json: dict[str, dict] = {}
        self.error: Exception | None = None

    def upload_file(self, content: bytes, filename: str) -> str:
        if self.error:
            raise self.error
        self.files[filename] = content
        return f"ipfs://image-{filename}"

    def upload_json(self, data: dict, name: str) -> str:
        self.json[name] = data
        return f"ipfs://meta-{name}"


class FakeContract:
    def __init__(self) -> None:
        self.uris: list[str] = []
        self.error: Exception | None = None

    def update_token_uri(self, token_uri: str) -> str:
        if self.error:
            raise self.error
        self.uris.append(token_uri)
        return "0xabc"


def make_fake_pipeline() -> Pipeline:
    return Pipeline(FakeHeadlines(), FakeImages(), FakeStorage(), FakeContract())
