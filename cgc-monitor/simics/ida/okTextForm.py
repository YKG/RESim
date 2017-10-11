'''
 * This software was created by United States Government employees
 * and may not be copyrighted.
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT,
 * INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
'''
from idaapi import Form
class okTextForm(Form):
    """Simple Form to test multilinetext and combo box controls"""
    def __init__(self, lines, prompt):
        self.prompt = prompt        
        print("in okTextForm init")
        if prompt:
            Form.__init__(self, r"""STARTITEM 0
BUTTON YES* OK
BUTTON NO NONE
BUTTON CANCEL NONE
CGC Ida Client Help

{FormChangeCb}
<Don't show help at startup:{nShow}>{cGroup1}>

{cStr1}
{cStr2}

""", {
            'cStr1': Form.StringLabel(lines['overview']),
            'cStr2': Form.StringLabel(lines['hotkeys']),
            'cGroup1': Form.ChkGroupControl(("nShow", "")),
            'FormChangeCb': Form.FormChangeCb(self.OnFormChange),
        })
       
        else:
            Form.__init__(self, r"""STARTITEM 0
BUTTON YES* OK
BUTTON NO NONE
BUTTON CANCEL NONE
CGC Ida Client Help

{FormChangeCb}
{cStr1}

""", {
            'cStr1': Form.StringLabel(lines['overview']),
            'cStr2': Form.StringLabel(lines['hotkeys']),
            'cGroup1': Form.ChkGroupControl(("nShow", "")),
            'FormChangeCb': Form.FormChangeCb(self.OnFormChange),
        })


    def OnFormChange(self, fid):
        return 1


    def go(self):
        print(" in go")
        f, args = self.Compile()
        #f.nShow.checked = False
        ok = f.Execute()
        print("is checked %r" % f.nShow.checked)
        f.Free()
        print(" out of go")
        if self.prompt:
            return f.nShow.checked
        else:
            return True
        

# --------------------------------------------------------------------------
def go(execute=True):
    """Test the multilinetext and combobox controls"""
    print(" in go")
    f = okTextForm()
    f, args = f.Compile()
    if execute:
        ok = f.Execute()
    else:
        print args[0]
        print args[1:]
        ok = 0

    print(" leaving go")
    f.Free()

