import random
import tempfile
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.challenge.mutations import make_challenges
from app.routes.deps import CurrentClaims
from app.routes.fixes import _unpack
from app.services.project_analyzer import analyze_files

router = APIRouter(prefix="/api/v1/challenge", tags=["comprehension fingerprint"])


@router.post("/mutations")
def mutations(
    file: UploadFile,
    claims: CurrentClaims,
    count: Annotated[int, Form(ge=1, le=5)] = 3,
    seed: Annotated[int | None, Form()] = None,
):
    """Seed one small defect into each of the project's most complex functions.

    The response contains the answers: only project-service may show the `code` to the
    student, never the `mutation`.
    """
    if claims.get("role") != "service":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal service endpoint")
    with tempfile.TemporaryDirectory(prefix="aipe-challenge-") as workdir:
        root, _archive = _unpack(file, workdir)
        # A seed makes a session reproducible (tests); production uses the system RNG.
        rng = random.Random(seed) if seed is not None else random.SystemRandom()  # noqa: S311
        challenges = make_challenges(root, analyze_files(root), count, rng)
        return {"challenges": [asdict(c) for c in challenges]}
