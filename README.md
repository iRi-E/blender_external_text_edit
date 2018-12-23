# External Text Edit

"External Text Edit" is a Blender addon to edit text in an external editor, even if the text is internal (not a separate file).

---

## Installation

1. Download "`external_text_edit.py`" file
1. In User Preferences window, install the addon file and enable it


## Setup

If the addon is enabled in the User Preferences window, "Preferences" box will appear just under there.

![setup](https://raw.githubusercontent.com/iRi-E/blender_external_text_edit/images/screenshot_setup.png)

You can use preset data if the text editor you want to use is listed in the "Preset" menu.
Otherwise, you have to manually specify the text editor, command line options, and whether the addon waits the external program terminated or not.

## Usage

### Start
1. Open Text Editor in Blender and create new text if no text exists
1. Select menu Text > External Text Editor > Start

![menu](https://raw.githubusercontent.com/iRi-E/blender_external_text_edit/images/screenshot_menu.png)

If the text is internal, a temporary file is created.

### Edit
1. Edit the text in the external text edior
1. Save the text, then the Blender's Text Editor will be updated immediately

![edit](https://raw.githubusercontent.com/iRi-E/blender_external_text_edit/images/screenshot_edit.png)

### Finish
1. Close the text you are editing in the external text editor
1. Select menu Text > External Text Editor > Stop

The step 2 above is unnecessary if "Wait for Return" is ON and correctly working.
The temporary file created for internal text is deleted automatically.
