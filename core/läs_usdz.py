from pxr import Usd, UsdGeom

def extrahera_koordinater(usdz_path: str) -> dict:
    stage = Usd.Stage.Open(usdz_path)
    result = {"väggar": [], "objekt": [], "golv": []}

    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        namn = prim.GetName()
        if "color" in namn.lower():
            continue

        xform     = UsdGeom.Xformable(prim)
        transform = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        pos       = transform.ExtractTranslation()
        koordinat = {"namn": namn, "x": round(pos[0], 3),
                     "y": round(pos[1], 3), "z": round(pos[2], 3)}

        if "Wall" in namn:
            result["väggar"].append(koordinat)
        elif "Floor" in namn:
            result["golv"].append(koordinat)
        else:
            result["objekt"].append(koordinat)

    return result