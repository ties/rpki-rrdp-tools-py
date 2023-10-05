import pathlib
from rrdp_tools.snapshot_rrdp import snapshot_rrdp

@pytest.mark.asyncio
async def test_reconstruct(tmp_path: pathlib.Path) -> None:
    await snapshot_rrdp("https://rrdp.ripe.net/notification.xml", tmp_path, include_session=True)
