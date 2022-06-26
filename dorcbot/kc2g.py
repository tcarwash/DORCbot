import requests


def muf(grid_from, grid_to):
    mofdata = requests.get(
        f"https://prop.kc2g.com/api/ptp.json?from_grid={grid_from}&to_grid={grid_to}&path=both"
    ).json()
    return mofdata[0].get("metrics")
