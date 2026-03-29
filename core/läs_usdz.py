from pxr import Usd, UsdGeom, Gf

def extrahera_koordinater(usdz_path: str) -> dict:
    stage  = Usd.Stage.Open(usdz_path)
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
        rotation  = transform.ExtractRotationQuat()
        im        = rotation.GetImaginary()
        re        = rotation.GetReal()

        # Bounding box
        mesh_prim       = UsdGeom.Mesh(prim)
        points          = mesh_prim.GetPointsAttr().Get()
        bredd, höjd, djup = 1.0, 2.0, 0.2

        if points:
            xs    = [p[0] for p in points]
            ys    = [p[1] for p in points]
            zs    = [p[2] for p in points]
            bredd = max(xs) - min(xs)
            höjd  = max(ys) - min(ys)
            djup  = max(zs) - min(zs)

        koordinat = {
            "namn":  namn,
            "x":     round(float(pos[0]), 3),
            "y":     round(float(pos[1]), 3),
            "z":     round(float(pos[2]), 3),
            "bredd": round(float(bredd), 3),
            "höjd":  round(float(höjd), 3),
            "djup":  round(float(djup), 3),
            "rot_x": round(float(im[0]), 4),
            "rot_y": round(float(im[1]), 4),
            "rot_z": round(float(im[2]), 4),
            "rot_w": round(float(re), 4),
        }

        if "Wall" in namn:
            result["väggar"].append(koordinat)
        elif "Floor" in namn:
            result["golv"].append(koordinat)
        else:
            result["objekt"].append(koordinat)

    return result