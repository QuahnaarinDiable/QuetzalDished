# SPDX-License-Identifier: LGPL-3.0-or-later
# GUI init for the Quetzal Dished Head add-on.
# Registers one command that inserts a dished head onto a selected Quetzal pipe
# port. The command is registered at startup so it can also be dropped into the
# Quetzal toolbar via Tools -> Customize -> Toolbars.

import os
import FreeCAD as App
import FreeCADGui as Gui

try:
    _DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _DIR = os.path.join(App.getUserAppDataDir(), "Mod", "QuetzalDished")
_ICON = os.path.join(_DIR, "Resources", "icons", "DishedHead.svg")


class _InsertDishedHead:
    def GetResources(self):
        return {
            "Pixmap": _ICON,
            "MenuText": "Insert Dished Head",
            "ToolTip": "Insert a dished head (torispherical / ellipsoidal / "
                       "hemispherical) on the selected Quetzal pipe end. "
                       "Switch HeadType and edit crown/knuckle in the Data tab.",
        }

    def Activated(self):
        try:
            import pDishedHead
            pDishedHead.doDishedHead()
        except ImportError:
            App.Console.PrintError(
                "Insert Dished Head requires the Quetzal workbench to be "
                "installed (it provides pFeatures / pCmd).\n")
        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return App.ActiveDocument is not None


class _InsertTube:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(_DIR, "Resources", "icons", "Tube.svg"),
            "MenuText": "Insert Tube (shell)",
            "ToolTip": "Insert a straight tube / shell course (a genuine Quetzal "
                       "Pipe) sized to the selected head or pipe and snapped on. "
                       "Edit its Height in the Data tab.",
        }

    def Activated(self):
        try:
            import pDishedHead
            pDishedHead.doTube()
        except ImportError:
            App.Console.PrintError(
                "Insert Tube requires the Quetzal workbench to be installed.\n")
        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand("Quetzal_InsertDishedHead", _InsertDishedHead())
Gui.addCommand("Quetzal_InsertShellTube", _InsertTube())


class _InsertFlange:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(_DIR, "Resources", "icons", "Flange.svg"),
            "MenuText": "Insert Flange",
            "ToolTip": "Insert a bolted flange ring (any size) sized to and "
                       "snapped onto the selected dished head or pipe port. "
                       "Edit FlangeOD / BoltCircle / NBolts in the Data tab.",
        }

    def Activated(self):
        try:
            import pDishedHead
            pDishedHead.doFlange()
        except ImportError:
            App.Console.PrintError(
                "Insert Flange requires the Quetzal workbench to be installed.\n")
        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand("Quetzal_InsertFlange", _InsertFlange())


class _InsertGasket:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(_DIR, "Resources", "icons", "Gasket.svg"),
            "MenuText": "Insert Gasket",
            "ToolTip": "Insert a gasket ring sized to and snapped onto the "
                       "selected flange's raised face.",
        }

    def Activated(self):
        try:
            import pDishedHead
            pDishedHead.doGasket()
        except ImportError:
            App.Console.PrintError(
                "Insert Gasket requires the Quetzal workbench to be installed.\n")
        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand("Quetzal_InsertGasket", _InsertGasket())


class _InsertNozzle:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(_DIR, "Resources", "icons", "Nozzle.svg"),
            "MenuText": "Insert Nozzle",
            "ToolTip": "Place a radial nozzle on the selected shell/pipe at a "
                       "distance along the axis and an angle around it. Avoids "
                       "Quetzal's outlet-dialog crash on standalone shells.",
        }

    def Activated(self):
        try:
            import pDishedHead
            pDishedHead.doNozzle()
        except ImportError:
            App.Console.PrintError(
                "Insert Nozzle requires the Quetzal workbench to be installed.\n")
        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand("Quetzal_InsertNozzle", _InsertNozzle())


class _ASMEThickness:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(_DIR, "Resources", "icons", "ASME.svg"),
            "MenuText": "ASME Thickness (size from pressure)",
            "ToolTip": "Compute the minimum shell and head thickness per "
                       "ASME VIII-1 from design pressure, allowable stress, joint "
                       "efficiency and corrosion allowance, and apply it to the "
                       "selected head or pipe.",
        }

    def Activated(self):
        try:
            import pDishedHead
            pDishedHead.doASMEThickness()
        except ImportError:
            App.Console.PrintError(
                "ASME Thickness requires the Quetzal workbench to be installed.\n")
        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand("Quetzal_ASMEThickness", _ASMEThickness())


class DishedHeadWorkbench(Gui.Workbench):
    MenuText = "Dished Heads"
    ToolTip = "Dished heads for Quetzal piping"
    Icon = _ICON

    def Initialize(self):
        cmds = ["Quetzal_InsertDishedHead", "Quetzal_InsertShellTube",
                "Quetzal_InsertNozzle", "Quetzal_InsertFlange",
                "Quetzal_InsertGasket", "Quetzal_ASMEThickness"]
        self.appendToolbar("Dished Heads", cmds)
        self.appendMenu("Dished Heads", cmds)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


try:
    Gui.addWorkbench(DishedHeadWorkbench())
except Exception:
    import traceback
    App.Console.PrintError(
        "Dished Heads workbench failed to load:\n" + traceback.format_exc())
