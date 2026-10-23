import requests


def muf(grid_from, grid_to):
    mofdata = requests.get(
        "https://prop.kc2g.com/api/ptp.json",
        params={"from_grid": grid_from, "to_grid": grid_to, "path": "both"},
        timeout=15,
    ).json()
    return mofdata[0].get("metrics")
