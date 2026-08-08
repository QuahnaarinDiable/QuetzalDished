# SPDX-License-Identifier: LGPL-3.0-or-later
# Dished head fitting for the Quetzal piping workbench.
#
# Adds a proper formed head (torispherical / ellipsoidal / hemispherical) as a
# first-class Quetzal "pype" object: a closed-walled solid with a bore, a single
# weld port, and PSize/PRating/PType so it snaps onto pipes and joins the BOM.
#
# This module IMPORTS Quetzal (pFeatures / pCmd) rather than copying it, so it
# tracks Quetzal's own base class and attachment helpers.  Requires the Quetzal
# workbench to be installed.

import math

import FreeCAD
import FreeCADGui
import Part

import pFeatures            # Quetzal base classes  (must be on the Mod path)
import pCmd                 # Quetzal attach/place helpers

QT = FreeCAD.Qt.QT_TRANSLATE_NOOP
V = FreeCAD.Vector

HEAD_TYPES = ["Torispherical", "Ellipsoidal", "Hemispherical"]


# --------------------------------------------- ASME VIII-1 thickness (int P) ---
# P, S in MPa (N/mm2); R, D, L, r in mm  ->  t in mm.  Internal pressure only.

def asme_shell(P, R, S, E):
    """UG-27: returns (hoop t, longitudinal t). Hoop governs the required t."""
    d1 = S * E - 0.6 * P
    d2 = 2 * S * E + 0.4 * P
    th = P * R / d1 if d1 > 0 else float("inf")
    tl = P * R / d2 if d2 > 0 else float("inf")
    return th, tl


def asme_ellipsoidal(P, D, S, E, ratio=2.0):
    """UG-32(d). K=(2+ratio^2)/6; K=1 for a 2:1 head."""
    K = (2.0 + ratio ** 2) / 6.0
    den = 2 * S * E - 0.2 * P
    return P * D * K / den if den > 0 else float("inf")


def asme_torispherical(P, L, r, S, E):
    """UG-32(e). M = 0.25*(3+sqrt(L/r)); L,r inside crown/knuckle radii."""
    if r <= 0:
        return float("inf")
    M = 0.25 * (3.0 + math.sqrt(L / r))
    den = 2 * S * E - 0.2 * P
    return P * L * M / den if den > 0 else float("inf")


def asme_hemispherical(P, R, S, E):
    """UG-32(f)."""
    den = 2 * S * E - 0.2 * P
    return P * R / den if den > 0 else float("inf")


# --------------------------------------------------------- geometry helpers ---

def _u(v):
    l = v.Length
    return V(v.x / l, v.y / l, v.z / l) if l > 1e-12 else V()


def _line(a, b):
    return Part.LineSegment(a, b).toShape()


def _arc(c, s, e):
    v1 = s.sub(c)
    v2 = e.sub(c)
    r = v1.Length
    m = c.add(_u(v1.add(v2)).multiply(r))
    return Part.Arc(s, m, e).toShape()


def _dome_edges(head, Rw, H, L, r, b):
    """Meridian edges from (Rw,0,H) up to the apex on the axis; returns (edges, apex_z).
    H is the top of the straight flange; the dome sits above it, in +Z."""
    if head == "Hemispherical":
        ap = H + Rw
        return [_arc(V(0, 0, H), V(Rw, 0, H), V(0, 0, ap))], ap
    if head == "Ellipsoidal":
        ap = H + b
        ell = Part.Ellipse(V(0, 0, 0), Rw, b)
        arc = Part.ArcOfEllipse(ell, 0.0, math.pi / 2.0).toShape()
        arc.rotate(V(0, 0, 0), V(1, 0, 0), 90.0)
        arc.translate(V(0, 0, H))
        return [arc], ap
    # Torispherical
    disc = (L - r) ** 2 - (Rw - r) ** 2
    if disc <= 0:
        ap = H + Rw
        return [_arc(V(0, 0, H), V(Rw, 0, H), V(0, 0, ap))], ap
    S = math.sqrt(disc)
    zc = H - S
    ap = zc + L
    kc = V(Rw - r, 0, H)
    cc = V(0, 0, zc)
    T = cc.add(_u(kc.sub(cc)).multiply(L))
    return [_arc(kc, V(Rw, 0, H), T), _arc(cc, T, V(0, 0, ap))], ap


def _revolve(head, Rw, H, L, r, b):
    edges, ap = _dome_edges(head, Rw, H, L, r, b)
    w = [_line(V(0, 0, 0), V(Rw, 0, 0)), _line(V(Rw, 0, 0), V(Rw, 0, H))]
    w.extend(edges)
    w.append(_line(V(0, 0, ap), V(0, 0, 0)))
    return Part.Face(Part.Wire(w)).revolve(V(0, 0, 0), V(0, 0, 1), 360.0)


# --------------------------------------------------------- the pype fitting ---

class DishedHead(pFeatures.pypeType):
    """PType='DishedHead' — a formed head that welds to a pipe/shell end.
    DishedHead(obj, rating, DN, OD, thk, head, L, r, sf, ratio)"""

    def __init__(self, obj, rating="SCH-STD", DN="DN50", OD=60.3, thk=3.0,
                 head="Torispherical", L=0.0, r=0.0, sf=0.0, ratio=2.0):
        super(DishedHead, self).__init__(obj)
        obj.PType = "DishedHead"
        obj.Proxy = self
        obj.PRating = rating
        obj.PSize = DN
        if L <= 0:
            L = OD                       # inside crown radius (F&D convention)
        if r <= 0:
            r = 0.1 * OD                 # inside knuckle radius
        if sf <= 0:
            sf = max(3.0 * thk, 25.0)    # straight flange
        obj.addProperty("App::PropertyLength", "OD", "DishedHead",
                        QT("App::Property", "Outside diameter")).OD = OD
        obj.addProperty("App::PropertyLength", "thk", "DishedHead",
                        QT("App::Property", "Wall thickness")).thk = thk
        obj.addProperty("App::PropertyLength", "ID", "DishedHead",
                        QT("App::Property", "Inside diameter")).ID = OD - 2 * thk
        obj.addProperty("App::PropertyEnumeration", "HeadType", "DishedHead",
                        QT("App::Property", "Formed head type"))
        obj.HeadType = HEAD_TYPES
        obj.HeadType = head if head in HEAD_TYPES else "Torispherical"
        obj.addProperty("App::PropertyLength", "CrownRadius", "DishedHead",
                        QT("App::Property", "Inside crown radius (torispherical)")).CrownRadius = L
        obj.addProperty("App::PropertyLength", "KnuckleRadius", "DishedHead",
                        QT("App::Property", "Inside knuckle radius (torispherical)")).KnuckleRadius = r
        obj.addProperty("App::PropertyFloat", "EllipseRatio", "DishedHead",
                        QT("App::Property", "Major:minor ratio (ellipsoidal; 2.0=2:1)")).EllipseRatio = ratio
        obj.addProperty("App::PropertyLength", "StraightFlange", "DishedHead",
                        QT("App::Property", "Straight flange height")).StraightFlange = sf
        obj.addProperty("App::PropertyString", "Profile", "DishedHead",
                        QT("App::Property", "Section dim.")).Profile = str(OD) + "x" + str(thk)
        obj.addProperty("App::PropertyLength", "DishDepth", "DishedHead",
                        QT("App::Property", "Internal dish depth"))
        obj.setEditorMode("DishDepth", 1)

        # ---- ASME VIII-1 design inputs (internal pressure) ------------------
        obj.addProperty("App::PropertyFloat", "DesignPressure", "ASME",
                        QT("App::Property", "Design pressure P, MPa (0 = ignore)")).DesignPressure = 0.0
        obj.addProperty("App::PropertyFloat", "AllowableStress", "ASME",
                        QT("App::Property", "Max allowable stress S, MPa")).AllowableStress = 138.0
        obj.addProperty("App::PropertyFloat", "JointEfficiency", "ASME",
                        QT("App::Property", "Weld joint efficiency E (0-1)")).JointEfficiency = 1.0
        obj.addProperty("App::PropertyLength", "CorrosionAllowance", "ASME",
                        QT("App::Property", "Corrosion allowance, mm")).CorrosionAllowance = 3.0
        obj.addProperty("App::PropertyLength", "RequiredThickness", "ASME",
                        QT("App::Property", "Min. required thickness incl. CA (read-only)"))
        obj.setEditorMode("RequiredThickness", 1)
        self.execute(obj)

    def onChanged(self, fp, prop):
        if prop == "ID" and fp.ID < fp.OD:
            fp.thk = (fp.OD - fp.ID) / 2

    def execute(self, fp):
        OD = fp.OD.Value
        t = fp.thk.Value
        if t > OD / 2:
            t = OD / 2.1
            fp.thk = t
        ID = OD - 2 * t
        fp.ID = ID
        fp.Profile = str(OD) + "x" + str(t)
        R = ID / 2.0
        Ro = OD / 2.0
        L = fp.CrownRadius.Value
        r = fp.KnuckleRadius.Value
        ratio = fp.EllipseRatio if fp.EllipseRatio > 0 else 2.0
        b = R / ratio
        sf = fp.StraightFlange.Value
        head = fp.HeadType
        if r >= R:
            r = 0.999 * R
        if head == "Torispherical" and L < R:
            L = R

        inner = _revolve(head, R, sf, L, r, b)
        outer = _revolve(head, Ro, sf, L + t, r + t, b + t)
        _, ap = _dome_edges(head, R, sf, L, r, b)
        fp.DishDepth = ap - sf
        fp.Shape = outer.cut(inner).removeSplitter()

        # live ASME required-thickness readout (does not drive geometry)
        try:
            fp.RequiredThickness = self._required(fp, R, ID, L, r, ratio, head)
        except Exception:
            pass

        # single weld port at the open annular face, pointing outward (-Z),
        # exactly like Quetzal's Cap so it mates onto a pipe end
        fp.Ports = [V(0, 0, 0)]
        fp.PortDirections = [V(0, 0, -1)]
        super(DishedHead, self).execute(fp)

    def _required(self, fp, R, ID, L, r, ratio, head):
        """ASME VIII-1 minimum thickness for this head + corrosion allowance."""
        P = float(fp.DesignPressure)
        S = float(fp.AllowableStress)
        E = float(fp.JointEfficiency)
        CA = fp.CorrosionAllowance.Value
        if P <= 0 or S <= 0 or E <= 0:
            return 0.0
        if head == "Hemispherical":
            t = asme_hemispherical(P, R, S, E)
        elif head == "Ellipsoidal":
            t = asme_ellipsoidal(P, ID, S, E, ratio)
        else:
            t = asme_torispherical(P, L, r, S, E)
        return (t + CA) if t != float("inf") else 0.0


# ------------------------------------------------------------- GUI commands ---

def makeDishedHead(propList=None, pos=None, Z=None, rating="SCH-STD",
                   head="Torispherical"):
    """Add a DishedHead. propList = [DN, OD, thk] (optional)."""
    if pos is None:
        pos = V(0, 0, 0)
    if Z is None:
        Z = V(0, 0, 1)
    a = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "DishedHead")
    if propList and len(propList) == 3:
        DishedHead(a, rating, propList[0], propList[1], propList[2], head=head)
    else:
        DishedHead(a, rating, head=head)
    pCmd.ViewProvider(a.ViewObject, "Quetzal_InsertCap")
    a.Placement.Base = pos
    a.Placement.Rotation = FreeCAD.Rotation(V(0, 0, 1), Z).multiply(a.Placement.Rotation)
    a.Label = "Dished Head"
    return a


def _ask(title, label, default, lo=1.0, hi=1.0e6):
    """Numeric input dialog, works on both PySide2 (Qt5) and PySide6 (Qt6)."""
    try:
        from PySide import QtWidgets as W
    except Exception:
        from PySide import QtGui as W
    val, ok = W.QInputDialog.getDouble(None, title, label, default, lo, hi, 1)
    return val, ok


def _ask_od_thk(title, od0=2500.0, thk0=12.0):
    """Prompt for OD and wall thickness (mm). Returns (od, thk) or None.
    Unlimited size — not tied to any pipe schedule table (rolled-plate shells)."""
    od, ok = _ask(title, "Outside diameter OD (mm):", od0, 10.0, 100000.0)
    if not ok:
        return None
    thk, ok = _ask(title, "Wall thickness (mm):", thk0, 1.0, 1000.0)
    if not ok:
        return None
    return od, thk


def doDishedHead(head="Torispherical", rating="SCH-STD", propList=None):
    """Insert a dished head. If a pipe/head is selected it matches and snaps to
    it; otherwise it asks for OD and wall thickness (any size, e.g. DN2500)."""
    doc = FreeCAD.activeDocument()
    doc.openTransaction("Insert dished head")
    try:
        sel = FreeCADGui.Selection.getSelectionEx()
        src = sel[0].Object if sel else None
        usable = bool(src) and hasattr(src, "Ports") and getattr(src, "PType", "Any") != "Any"
        pos, Z, srcObj, srcPort = pCmd.getAttachmentPoints()
        if usable and propList is None and hasattr(srcObj, "OD"):
            propList = [getattr(srcObj, "PSize", "DN50"),
                        srcObj.OD.Value, srcObj.thk.Value]
            rating = getattr(srcObj, "PRating", rating) or rating
        if propList is None:                       # no size from selection -> ask
            r = _ask_od_thk("Dished Head")
            if r is None:
                doc.abortTransaction()
                return
            od, thk = r
            propList = ["DN%d" % int(round(od)), od, thk]
        head_obj = makeDishedHead(propList, pos, Z, rating, head)
        doc.commitTransaction()
        doc.recompute()
        if usable:
            pCmd.alignTwoPorts(head_obj, 0, srcObj, srcPort)
    except Exception as e:
        FreeCAD.Console.PrintWarning("DishedHead: %s\n" % e)
        try:
            doc.abortTransaction()
        except Exception:
            pass
    doc.recompute()


def doTube(length=500.0, rating="SCH-STD", propList=None):
    """Insert a straight tube (shell course) as a genuine Quetzal Pipe, sized to
    a selected head/pipe and snapped onto its port. It IS a Quetzal Pipe, so it
    is compatible with every Quetzal tool (BOM, mate, pypeline, colouring)."""
    doc = FreeCAD.activeDocument()
    doc.openTransaction("Insert tube")
    try:
        sel = FreeCADGui.Selection.getSelectionEx()
        src = sel[0].Object if sel else None
        usable = bool(src) and hasattr(src, "Ports") and getattr(src, "PType", "Any") != "Any"
        pos, Z, srcObj, srcPort = pCmd.getAttachmentPoints()
        if usable and propList is None and hasattr(srcObj, "OD"):
            # match the selected head/pipe; only ask for the length
            ln, ok = _ask("Tube", "Length (mm):", length, 10.0, 1000000.0)
            if not ok:
                doc.abortTransaction()
                return
            propList = [getattr(srcObj, "PSize", "DN50"),
                        srcObj.OD.Value, srcObj.thk.Value, ln]
            rating = getattr(srcObj, "PRating", rating) or rating
        elif propList is None:                     # standalone -> ask OD, thk, length
            r = _ask_od_thk("Tube")
            if r is None:
                doc.abortTransaction()
                return
            od, thk = r
            ln, ok = _ask("Tube", "Length (mm):", length, 10.0, 1000000.0)
            if not ok:
                doc.abortTransaction()
                return
            propList = ["DN%d" % int(round(od)), od, thk, ln]
        tube = pCmd.makePipe(rating, propList, pos, Z)
        doc.commitTransaction()
        doc.recompute()
        if usable:
            pCmd.alignTwoPorts(tube, 0, srcObj, srcPort)
    except Exception as e:
        FreeCAD.Console.PrintWarning("Tube: %s\n" % e)
        try:
            doc.abortTransaction()
        except Exception:
            pass
    doc.recompute()


def _ceil_mm(x):
    return float(math.ceil(x - 1e-9))


def doASMEThickness():
    """Size a shell/head from design pressure per ASME VIII-1. Reads a selected
    head/pipe (or asks for the diameter), prompts P/S/E/CA, reports the required
    thickness for the shell and every head type, and applies it to the selection."""
    doc = FreeCAD.activeDocument()
    if doc is None:
        return
    sel = FreeCADGui.Selection.getSelectionEx()
    obj = sel[0].Object if sel else None
    if obj is not None and hasattr(obj, "OD"):
        OD = obj.OD.Value
        tc = obj.thk.Value
        ID = OD - 2 * tc
    else:
        d, ok = _ask("ASME sizing", "Inside diameter D (mm):", 2500.0, 10.0, 100000.0)
        if not ok:
            return
        ID = d
    R = ID / 2.0
    P, ok = _ask("ASME sizing", "Design pressure P (MPa):", 1.0, 0.0, 1000.0)
    if not ok:
        return
    S, ok = _ask("ASME sizing", "Max allowable stress S (MPa):", 138.0, 1.0, 100000.0)
    if not ok:
        return
    E, ok = _ask("ASME sizing", "Joint efficiency E (0-1):", 1.0, 0.1, 1.0)
    if not ok:
        return
    CA, ok = _ask("ASME sizing", "Corrosion allowance (mm):", 3.0, 0.0, 100.0)
    if not ok:
        return

    th, tl = asme_shell(P, R, S, E)
    te = asme_ellipsoidal(P, ID, S, E, 2.0)
    if obj is not None and hasattr(obj, "CrownRadius"):
        L = obj.CrownRadius.Value
        r = obj.KnuckleRadius.Value
    else:
        L, r = ID, 0.06 * ID
    tt = asme_torispherical(P, L, r, S, E)
    tsph = asme_hemispherical(P, R, S, E)
    shell_req = _ceil_mm(th + CA)

    report = "\n".join([
        "ASME VIII-1 (internal pressure)  P=%.3f MPa  S=%.1f  E=%.2f  CA=%.1f mm  ID=%.0f mm" % (P, S, E, CA, ID),
        "  Shell hoop (governs) : %6.2f + CA = %6.2f  ->  use %.0f mm" % (th, th + CA, shell_req),
        "  Shell longitudinal   : %6.2f mm" % tl,
        "  2:1 ellipsoidal head : %6.2f + CA = %6.2f mm" % (te, te + CA),
        "  Torispherical L=%.0f r=%.0f: %6.2f + CA = %6.2f mm" % (L, r, tt, tt + CA),
        "  Hemispherical head   : %6.2f + CA = %6.2f mm" % (tsph, tsph + CA),
    ])
    FreeCAD.Console.PrintMessage(report + "\n")

    applied = None
    if obj is not None and getattr(obj, "PType", "") == "DishedHead":
        obj.DesignPressure = P
        obj.AllowableStress = S
        obj.JointEfficiency = E
        obj.CorrosionAllowance = CA
        ht = obj.HeadType
        if ht == "Hemispherical":
            req = tsph
        elif ht == "Ellipsoidal":
            req = asme_ellipsoidal(P, ID, S, E, obj.EllipseRatio or 2.0)
        else:
            req = asme_torispherical(P, obj.CrownRadius.Value, obj.KnuckleRadius.Value, S, E)
        newt = _ceil_mm(req + CA)
        obj.thk = newt
        applied = ("head (%s)" % ht, newt)
        doc.recompute()
    elif obj is not None and hasattr(obj, "thk") and hasattr(obj, "OD"):
        obj.thk = shell_req
        applied = ("shell / pipe", shell_req)
        doc.recompute()

    try:
        try:
            from PySide import QtWidgets as W
        except Exception:
            from PySide import QtGui as W
        msg = report
        if applied:
            msg += "\n\nApplied to %s:  thk = %.0f mm" % (applied[0], applied[1])
        else:
            msg += "\n\n(Select a Dished Head or a pipe first to apply a value.)"
        W.QMessageBox.information(None, "ASME thickness", msg)
    except Exception:
        pass


# ------------------------------------------------- bolted flange (any size) ---

class Flange(pFeatures.pypeType):
    """PType='Flange' — a bolted flange ring of any diameter, welding to a pipe
    or dished-head port. Not bound to schedule tables, so it works for a DN50
    nozzle or a DN2500 body/manway flange alike."""

    def __init__(self, obj, rating="PN16", DN="DN50", pipeOD=60.3, pipeThk=3.0,
                 flangeOD=0.0, flangeThk=0.0, bcd=0.0, nbolts=8, boltdia=18.0):
        super(Flange, self).__init__(obj)
        obj.PType = "Flange"
        obj.Proxy = self
        obj.PRating = rating
        obj.PSize = DN
        if flangeOD <= 0:
            flangeOD = pipeOD * 1.5 + 20.0
        if flangeThk <= 0:
            flangeThk = max(pipeOD * 0.06, 12.0)
        if bcd <= 0:
            bcd = (pipeOD + flangeOD) / 2.0
        obj.addProperty("App::PropertyLength", "PipeOD", "Flange",
                        QT("App::Property", "Matching pipe/shell OD")).PipeOD = pipeOD
        obj.addProperty("App::PropertyLength", "PipeThk", "Flange",
                        QT("App::Property", "Matching wall thickness")).PipeThk = pipeThk
        obj.addProperty("App::PropertyLength", "FlangeOD", "Flange",
                        QT("App::Property", "Flange outside diameter")).FlangeOD = flangeOD
        obj.addProperty("App::PropertyLength", "FlangeThk", "Flange",
                        QT("App::Property", "Flange thickness")).FlangeThk = flangeThk
        obj.addProperty("App::PropertyLength", "BoltCircle", "Flange",
                        QT("App::Property", "Bolt circle diameter")).BoltCircle = bcd
        obj.addProperty("App::PropertyInteger", "NBolts", "Flange",
                        QT("App::Property", "Number of bolt holes")).NBolts = nbolts
        obj.addProperty("App::PropertyLength", "BoltDia", "Flange",
                        QT("App::Property", "Bolt hole diameter")).BoltDia = boltdia
        obj.addProperty("App::PropertyLength", "ID", "Flange",
                        QT("App::Property", "Bore")).ID = pipeOD - 2 * pipeThk
        obj.addProperty("App::PropertyString", "Profile", "Flange",
                        QT("App::Property", "Section")).Profile = str(flangeOD) + "x" + str(flangeThk)
        obj.addProperty("App::PropertyEnumeration", "FaceType", "Flange",
                        QT("App::Property", "Facing type"))
        obj.FaceType = ["Flat", "Raised"]
        obj.FaceType = "Raised"
        obj.addProperty("App::PropertyLength", "RaisedFaceDia", "Flange",
                        QT("App::Property", "Raised-face diameter")).RaisedFaceDia = pipeOD * 1.15 + 10.0
        obj.addProperty("App::PropertyLength", "RaisedFaceThk", "Flange",
                        QT("App::Property", "Raised-face height")).RaisedFaceThk = 2.0
        obj.addProperty("App::PropertyLength", "HubLength", "Flange",
                        QT("App::Property", "Weld-neck hub length (0 = slip-on)")).HubLength = 0.0
        obj.addProperty("App::PropertyLength", "HubDia", "Flange",
                        QT("App::Property", "Hub diameter at the flange back")).HubDia = pipeOD * 1.25 + 8.0
        self.execute(obj)

    def onChanged(self, fp, prop):
        pass

    def execute(self, fp):
        OD = fp.PipeOD.Value
        t = fp.PipeThk.Value
        bore = max(OD - 2 * t, 1.0)
        Df = fp.FlangeOD.Value
        tf = fp.FlangeThk.Value
        bcd = fp.BoltCircle.Value
        n = max(int(fp.NBolts), 0)
        bd = fp.BoltDia.Value
        face = fp.FaceType
        rfd = fp.RaisedFaceDia.Value
        rft = fp.RaisedFaceThk.Value
        hub = fp.HubLength.Value
        fp.ID = bore
        fp.Profile = str(Df) + "x" + str(tf)

        solid = Part.makeCylinder(Df / 2.0, tf).cut(Part.makeCylinder(bore / 2.0, tf))
        mate_z = tf
        if face == "Raised" and rft > 0:
            rf = Part.makeCylinder(rfd / 2.0, rft, V(0, 0, tf), V(0, 0, 1)).cut(
                 Part.makeCylinder(bore / 2.0, rft + 1.0, V(0, 0, tf), V(0, 0, 1)))
            solid = solid.fuse(rf)
            mate_z = tf + rft
        weld_z = 0.0
        if hub > 0:
            r_base = max(fp.HubDia.Value / 2.0, OD / 2.0 + 1.0)
            cone = Part.makeCone(r_base, OD / 2.0, hub, V(0, 0, 0), V(0, 0, -1))
            cone = cone.cut(Part.makeCylinder(bore / 2.0, hub + 2.0, V(0, 0, 1.0), V(0, 0, -1)))
            solid = solid.fuse(cone)
            weld_z = -hub

        for i in range(n):
            a = 2.0 * math.pi * i / n
            c = V(bcd / 2.0 * math.cos(a), bcd / 2.0 * math.sin(a), -1.0)
            solid = solid.cut(Part.makeCylinder(bd / 2.0, tf + 2.0, c, V(0, 0, 1)))

        fp.Shape = solid.removeSplitter()
        # port 0 = weld side (to pipe/head), port 1 = bolted mating (raised) face
        fp.Ports = [V(0, 0, weld_z), V(0, 0, mate_z)]
        fp.PortDirections = [V(0, 0, -1), V(0, 0, 1)]
        super(Flange, self).execute(fp)


def makeVesselFlange(propList=None, pos=None, Z=None, rating="PN16"):
    if pos is None:
        pos = V(0, 0, 0)
    if Z is None:
        Z = V(0, 0, 1)
    a = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "Flange")
    if propList and len(propList) >= 4:
        Flange(a, rating, propList[0], propList[1], propList[2], propList[3])
    else:
        Flange(a, rating)
    pCmd.ViewProvider(a.ViewObject, "Quetzal_InsertFlange")
    a.Placement.Base = pos
    a.Placement.Rotation = FreeCAD.Rotation(V(0, 0, 1), Z).multiply(a.Placement.Rotation)
    a.Label = "Flange"
    return a


def doFlange(rating="PN16"):
    """Insert a bolted flange, sized to and snapped onto the selected head/pipe
    port. Edit FlangeOD / BoltCircle / NBolts in the Data tab to suit."""
    doc = FreeCAD.activeDocument()
    doc.openTransaction("Insert flange")
    try:
        sel = FreeCADGui.Selection.getSelectionEx()
        src = sel[0].Object if sel else None
        usable = bool(src) and hasattr(src, "Ports") and getattr(src, "PType", "Any") != "Any"
        pos, Z, srcObj, srcPort = pCmd.getAttachmentPoints()
        propList = None
        if usable and hasattr(srcObj, "OD"):
            od = srcObj.OD.Value
            thk = srcObj.thk.Value if hasattr(srcObj, "thk") else max(od * 0.02, 3.0)
            propList = [getattr(srcObj, "PSize", "DN50"), od, thk, 0.0]
            rating = getattr(srcObj, "PRating", rating) or rating
        fl = makeVesselFlange(propList, pos, Z, rating)
        doc.commitTransaction()
        doc.recompute()
        if usable:
            pCmd.alignTwoPorts(fl, 0, srcObj, srcPort)
    except Exception as e:
        FreeCAD.Console.PrintWarning("Flange: %s\n" % e)
        try:
            doc.abortTransaction()
        except Exception:
            pass
    doc.recompute()


# ---------------------------------------------------------------- gasket ------

class Gasket(pFeatures.pypeType):
    """PType='Gasket' — a thin ring that seats on a raised face between flanges."""

    def __init__(self, obj, rating="PN16", DN="DN50", OD=90.0, ID=60.0, thk=3.0):
        super(Gasket, self).__init__(obj)
        obj.PType = "Gasket"
        obj.Proxy = self
        obj.PRating = rating
        obj.PSize = DN
        obj.addProperty("App::PropertyLength", "OD", "Gasket",
                        QT("App::Property", "Gasket outside diameter")).OD = OD
        obj.addProperty("App::PropertyLength", "ID", "Gasket",
                        QT("App::Property", "Gasket inside diameter")).ID = ID
        obj.addProperty("App::PropertyLength", "Thickness", "Gasket",
                        QT("App::Property", "Gasket thickness")).Thickness = thk
        self.execute(obj)

    def onChanged(self, fp, prop):
        pass

    def execute(self, fp):
        OD = fp.OD.Value
        ID = fp.ID.Value
        th = fp.Thickness.Value
        if ID >= OD:
            ID = 0.7 * OD
        fp.Shape = Part.makeCylinder(OD / 2.0, th).cut(
            Part.makeCylinder(ID / 2.0, th)).removeSplitter()
        fp.Ports = [V(0, 0, 0), V(0, 0, th)]
        fp.PortDirections = [V(0, 0, -1), V(0, 0, 1)]
        super(Gasket, self).execute(fp)


def makeGasket(propList=None, pos=None, Z=None, rating="PN16"):
    if pos is None:
        pos = V(0, 0, 0)
    if Z is None:
        Z = V(0, 0, 1)
    a = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "Gasket")
    if propList and len(propList) >= 4:
        Gasket(a, rating, propList[0], propList[1], propList[2], propList[3])
    else:
        Gasket(a, rating)
    pCmd.ViewProvider(a.ViewObject, "Quetzal_InsertFlange")
    a.Placement.Base = pos
    a.Placement.Rotation = FreeCAD.Rotation(V(0, 0, 1), Z).multiply(a.Placement.Rotation)
    a.Label = "Gasket"
    return a


def doGasket(rating="PN16"):
    """Insert a gasket sized to and snapped onto a selected flange's face."""
    doc = FreeCAD.activeDocument()
    doc.openTransaction("Insert gasket")
    try:
        sel = FreeCADGui.Selection.getSelectionEx()
        src = sel[0].Object if sel else None
        usable = bool(src) and hasattr(src, "Ports") and getattr(src, "PType", "Any") != "Any"
        pos, Z, srcObj, srcPort = pCmd.getAttachmentPoints()
        propList = None
        if usable and getattr(srcObj, "PType", "") == "Flange":
            od = srcObj.RaisedFaceDia.Value if hasattr(srcObj, "RaisedFaceDia") \
                else srcObj.FlangeOD.Value * 0.8
            idi = srcObj.ID.Value if hasattr(srcObj, "ID") else od * 0.7
            propList = [getattr(srcObj, "PSize", "DN50"), od, idi, 3.0]
            rating = getattr(srcObj, "PRating", rating) or rating
        gk = makeGasket(propList, pos, Z, rating)
        doc.commitTransaction()
        doc.recompute()
        if usable:
            # mate to the flange's face port (highest-numbered port)
            port = srcPort if srcPort is not None else (len(srcObj.Ports) - 1)
            pCmd.alignTwoPorts(gk, 0, srcObj, port)
    except Exception as e:
        FreeCAD.Console.PrintWarning("Gasket: %s\n" % e)
        try:
            doc.abortTransaction()
        except Exception:
            pass
    doc.recompute()


# ----------------------------------------------- radial nozzle on a shell -----

def _ask_size(title="Nozzle size"):
    """Two-step standard picker: pick a DN pipe schedule (SCH-STD, SCH-40, ...)
    then a DN size within it. Ignores conduit/rebar tables entirely.
    Returns (DN, OD, thk, schedule) or None."""
    import os
    try:
        tdir = os.path.join(os.path.dirname(pCmd.__file__), "tablez")
        scheds = sorted(f[5:-4] for f in os.listdir(tdir)
                        if f.startswith("Pipe_SCH") and f.endswith(".csv"))
    except Exception:
        scheds = ["SCH-STD"]
    if not scheds:
        scheds = ["SCH-STD"]
    try:
        from PySide import QtWidgets as W
    except Exception:
        from PySide import QtGui as W
    sdef = scheds.index("SCH-STD") if "SCH-STD" in scheds else 0
    sched, ok = W.QInputDialog.getItem(None, title, "Pipe schedule:",
                                       scheds, sdef, False)
    if not ok:
        return None
    try:
        rows = pCmd.readTable("Pipe_%s.csv" % sched)
    except Exception:
        return None
    if not rows:
        return None
    items = ["%s   (OD %s mm x %s)" % (r.get("PSize", "?"), r.get("OD", "?"),
                                       r.get("thk", "?")) for r in rows]
    ddef = 0
    for i, r in enumerate(rows):
        if r.get("PSize") == "DN100":
            ddef = i
            break
    text, ok = W.QInputDialog.getItem(None, title, "DN size (%s):" % sched,
                                      items, ddef, False)
    if not ok:
        return None
    r = rows[items.index(text)]
    try:
        return r.get("PSize", "DN?"), float(r["OD"]), float(r["thk"]), sched
    except Exception:
        return None


def doNozzle():
    """Place a radial nozzle on the selected shell/pipe at a distance along the
    axis (from Port 0) and an angle around it. The nozzle is a genuine Quetzal
    Pipe stub positioned by geometry — no PypeLine, no outlet dialog, so it
    cannot hit Quetzal's moveToPyLi/.Group crash. Weld a flange to its outboard
    end with Insert Flange."""
    doc = FreeCAD.activeDocument()
    sel = FreeCADGui.Selection.getSelection()
    shell = sel[0] if sel else None
    if shell is None or not hasattr(shell, "OD") or not hasattr(shell, "Height"):
        FreeCAD.Console.PrintError(
            "Insert Nozzle: select the shell/pipe first (a Quetzal pipe/tube).\n")
        return
    Ro = shell.OD.Value / 2.0
    H = shell.Height.Value
    size = _ask_size()
    if size is None:
        return
    dn, od, thk, rating = size
    length, ok = _ask("Nozzle", "Projection beyond shell (mm):", 150.0, 5.0, 100000.0)
    if not ok:
        return
    d, ok = _ask("Nozzle", "Distance from Port 0 along shell (mm):", H / 2.0, 0.0, H)
    if not ok:
        return
    ang, ok = _ask("Nozzle", "Angle around shell (deg):", 0.0, -360.0, 360.0)
    if not ok:
        return

    a = math.radians(ang)
    d = min(max(d, 0.0), H)
    local_pos = V(Ro * math.cos(a), Ro * math.sin(a), d)     # on the outer wall
    local_dir = V(math.cos(a), math.sin(a), 0.0)             # radial outward
    pos = shell.Placement.multVec(local_pos)
    Zdir = shell.Placement.Rotation.multVec(local_dir)

    doc.openTransaction("Insert nozzle")
    try:
        noz = pCmd.makePipe(rating, [dn, od, thk, length], pos, Zdir)
        noz.Label = "Nozzle"
        doc.commitTransaction()
    except Exception as e:
        FreeCAD.Console.PrintWarning("Nozzle: %s\n" % e)
        try:
            doc.abortTransaction()
        except Exception:
            pass
    doc.recompute()
