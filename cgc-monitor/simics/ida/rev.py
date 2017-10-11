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
import time
import idaapi
import gdbProt
import bookmarkView
import okTextForm
import waitDialog
from idaapi import Choose
'''
    Ida script to reverse execution of Simics to the next breakpoint.
    Since Ida does not know about reverse exectution, the general approach is to 
    tell Simics to reverse and then tell Ida to continue forward.
    The script installs its functions as a hotkeys. 
    See showHelp below
'''
__regs =['eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp', 'ax', 'bx', 'cx', 'dx']
recent_bookmark = 1
just_debug = False
bookmark_view = bookmarkView.bookmarkView()
print('back from init bookmarkView')
keymap_done = False
def disableAllBpts(exempt):
    qty = idc.GetBptQty()
    disabledSet = []
    for i in range(qty):
	bptEA = GetBptEA(i)
        bptStat = CheckBpt(bptEA)
	if bptStat > 0:
	    if exempt is None or exempt != bptEA:
	        disabledSet.append(bptEA)
	        EnableBpt(bptEA, False)
    return disabledSet

def enableBpts(disabledSet):
    for ea in disabledSet:
	EnableBpt(ea, True)

def showHelp(prompt=False):
    print('in showHelp')
    lines = {}
    lines['overview'] = """
CGC Monitor Ida Client Help
The Ida gdb client is enhanced to support reverse execution; use of
execution bookmarks; and functions such as reversing until a specified
register is modified.  The functions are available through the "Debug"
menu.   Ida has also been extended to include a "Bookmarks" tabbed window
that lists execution bookmarks, which can be appended via a right click.

The GCC Monitor will have broken execution at a PoV or signal, as reflected
in the last bookmark in the Bookmarks tabbed window.

    """
    lines['hotkeys'] = """
The script installs its functions as a hotkeys. Note use <fn> key on Mac 
 
    Alt-Shift-F9 reverse
    Alt-Shift-F8 reverse step over
    Alt-Shift-F7 reverse step into 
    Alt-Shift-F4 reverse to cursor
    Alt-F6       reverse until just before current function is called
    Alt-Shift-r  reverse to previous write to highlighted register
    Alt-Shift-a  reverse to previous write to highlighted (or entered) address
    Alt-Shift-s  reverse to previous write to current stack location
    Alt-Shift-o  jump to initial debug eip (just before fault) 
    Alt-Shift-t  jump to start of process
    Alt-Shift-p  set an execution bookmark
    Alt-Shift-j  jump to a bookmark (chosen from list)
    Alt-Shift-u  run forward until in user space (useful if found missing page)
    Alt-Shift-q  quit ida debug session
    Alt-Shift-h  show help
    """
    print lines['hotkeys']
    print('do okTextForm')
    f = okTextForm.okTextForm(lines, prompt)
    return f.go()

'''
    Read a return string generated by Simics and parse out the EIP
'''
def getAddress(simicsString):
    if simicsString is None or type(simicsString) is int:
        return None
    # simics 4.8 is spitting multiple lines when it hits a break or cycle
    line = None
    try:
        lines = simicsString.split('\n')
    except:
        print('getAddress failed splitting lines')
        return None
    # hack to get the last simics output with an eip in it
    for line in reversed(lines):
        #print 'check %s' % line
        if 'cs:' in line or 'ip:' in line:
            simicsString = line
            break
    #print('new string is %s' % simicsString)
    toks = None
    try:
        toks = simicsString.split(' ')
    except:
	print 'getAddress not a string to split'
	return None
    addr = None
    for tok in toks:
        #print 'look at tok [%s]' % tok
        if tok.find("skip_this_address") != -1:
            print 'SKIP THIS ADDRESS' 
            return 0
	if tok.startswith('cs:') or tok.startswith('ip:'):
		#print 'got cs! %s' % tok
                try:
		    addr = int(tok[3:], 16)
                except:
                    print('exception in getAddress trying to get int from tok %s' % tok)
                    print('failed to get int 16 from %s' % tok[3:])
		break
    return addr

def setAndDisable(addr):
    bptEnabled = idc.CheckBpt(addr)
    if bptEnabled < 0:
	# no breakpoint, add one
	#print 'setAndDisable no bpt at %x, add one' % addr
	idc.AddBpt(addr)
    elif bptEnabled == 0:
	# breakpoint, but not enabled
	#print 'found bpt at %x, enable it' % addr
        idc.EnableBpt(addr, True)
    else:
	#print 'breakpoint exists, use it'
	pass
    # disable all breakpoints, excempting the one we just set/enabled
    disabledSet = disableAllBpts(addr)
    return bptEnabled, disabledSet

def reEnable(addr, bptEnabled, disabledSet):
    enableBpts(disabledSet)
    #print 'back from enable'
    if bptEnabled < 0:
        idc.EnableBpt(addr, False)
        success = idc.DelBpt(addr)
        #print 'reEnable delete bpt at %x success: %d' % (addr, success)
    elif bptEnabled == 0:
        #print 'reEnable reenabling bkpt at %x' % addr
	idc.EnableBpt(addr, False)


'''
    reverse-step-instruction, but within current process, return new eip
'''
def reverseStepInstruction(num=1):

    command = "@cgc.reverseStepInstruction(%d)" % num
    simicsString = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    #simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.reverseToCallInstruction(True)");')
    eip = gdbProt.getEIPWhenStopped()
    return eip

def doRevStepOver():
    #print 'in doRevStepOver'
    curAddr = idc.GetRegValue("EIP")
    prev_eip = idc.PrevAddr(curAddr)
    simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.reverseToCallInstruction(False, prev=0x%x)");' % prev_eip)
    eip = gdbProt.getEIPWhenStopped()
    gdbProt.stepWait()
    return eip

def doRevStepInto():
    #print 'in doRevStepInto'
    #eip = reverseStepInstruction()
    curAddr = idc.GetRegValue("EIP")
    prev_eip = idc.PrevAddr(curAddr)
    simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.reverseToCallInstruction(True, prev=0x%x)");' % prev_eip)
    eip = gdbProt.getEIPWhenStopped()
    gdbProt.stepWait()
    return eip

def doRevFinish():
    #print 'doRevFinish'
    #doRevCommand('uncall-function')
    cur_addr = idc.GetRegValue("EIP")
    f = GetFunctionAttr(cur_addr, FUNCATTR_START)
    if f != BADADDR: 
        print('got function start, go there, and further back 1') 
        doRevToAddr(f, 1)
    else:
        print('use monitor uncall function')
        simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.uncall()");')
        eip = gdbProt.getEIPWhenStopped()
        gdbProt.stepWait()

'''
    Issue the Simics "rev" command via GDB and then move forward the actual breakpoint
'''
def doReverse(extra_back=None):
    #print 'in doReverse'
    curAddr = idc.GetRegValue("EIP")
    goNowhere()
    #print('doReverse, back from goNowhere curAddr is %x' % curAddr)
    isBpt = idc.CheckBpt(curAddr)
    # if currently at a breakpoint, we need to back an instruction to so we don't break
    # here
    if isBpt > 0:
	#print 'curAddr is %x, it is a breakpoint, do a rev step over' % curAddr
        addr = doRevStepOver()
        #print 'in doReverse, did RevStepOver got addr of %x' % addr
        isBpt = idc.CheckBpt(addr)
        if isBpt > 0:
	    # back up onto a breakpoint, we are done
            #print('doReverse backed to breakpoint, we are done')
	    return addr

    #print 'do reverse'
    param = ''
    if extra_back is not None:
        param = extra_back
    command = '@cgc.doReverse(%s)' % param
    simicsString = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    addr = gdbProt.getEIPWhenStopped()
    #print 'reverse addr after stop %x' % addr
    #GetDebuggerEvent(WFNE_SUSP , 5)
    #print 'back from getdebugevent'
    disabledSet = disableAllBpts(None)
    #print 'after disable'
    gdbProt.stepWait()
    #print 'after stepInto'
    enableBpts(disabledSet)
    #print 'after enable'

    return addr

''' reverse to the given address, but hit any existing breakpoints '''
def doRevToAddr(addr, extra_back=None):

    # set a breakpoint for the address 
    bptEnabled = idc.CheckBpt(addr)
    bptNumber = None
    if bptEnabled < 0:
	# no breakpoint where addr was, add one
	print 'doRevToAddr no bpt where at addr %x, add one' % addr
	retval = idc.AddBpt(addr)
    elif bptEnabled == 0:
	# breakpoint, but not enabled
	print 'found bpt at %x, enable it' % addr
        idc.EnableBpt(addr, True)
    else:
	print 'breakpoint exists, use it'
    # now run backwards and see if we reach that breakpoint
    new_addr = doReverse(extra_back)

    curAddr = idc.GetRegValue("EIP")
    if curAddr == addr: # we reached it
	#print 'did reach addr'
        pass
    else:
	print('did not reach addr stopped at 0x%x addr is 0x%x, doReverse said 0x %x' % (curAddr, addr, new_addr))

    if bptEnabled < 0:
	idc.DelBpt(addr)
    elif bptEnabled == 0:
        idc.EnableBpt(addr, False)

def doRevToCursor():
    cursor = ScreenEA()
    curAddr = idc.GetRegValue("EIP")
    if cursor == curAddr:
        print 'attempt to go back to where you are ignored'
        return
    doRevToAddr(cursor)

def getCPL():
    cs = idc.GetRegValue("CS")
    return cs & 3
'''
Run backwards until we find the most recent write to the current SP
'''
def wroteToSP():
    sp = idc.GetRegValue("ESP")
    print 'Running backwards to previous write to ESP:0x%x' % sp
    wroteToAddress(sp)
 
def registerMath(): 
    #regs =['eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp']
    highlighted = idaapi.get_highlighted_identifier()
    retval = None
    if highlighted is not None:
        print 'highlighted is %s' % highlighted
        if highlighted in __regs:
            retval = idc.GetRegValue(highlighted)
        else:
            try:
                retval = int(highlighted, 16)
            except:
                pass
            if retval is None:
                for reg in __regs:
                    if highlighted.startswith(reg):
                        rest = highlighted[len(reg):]
                        value = None
                        try:
                            value = int(rest[1:])
                        except:
                            pass
                        if value is not None:
                            if rest.startswith('+'):
                                regvalue = idc.GetRegValue(reg)
                                retval = regvalue + value
                            elif rest.startswith('-'):
                                regvalue = idc.GetRegValue(reg)
                                retval = regvalue - value
    return retval
                    
                    
def getMailbox():    
    msg = gdbProt.Evalx('SendGDBMonitor("@cgc.emptyMailbox()");')
    lines = msg.split('\n')
    if len(lines) > 1:
        msg = lines[0]
    print 'got mailbox message: <%s>' % msg
    return msg

def getUIAddress():    
    value = registerMath()
    if value is None:
        value = idc.GetRegValue("ESP")
    target_addr = AskAddr(value, "run backwards until this address is modified:")
    return target_addr

def wroteToAddressPrompt():
    addr = getUIAddress()
    print('Running backwards to find write to address 0x%x' % addr)
    wroteToAddress(addr)

def wroteToAddress(target_addr):
    disabledSet = disableAllBpts(None)
    command = '@cgc.stopAtKernelWrite(0x%x)' % target_addr
    simicsString = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    eip = gdbProt.getEIPWhenStopped()
    gdbProt.stepWait()
    enableBpts(disabledSet)
    if eip >=  0xc0000000:
        print('previous syscall wrote to address 0x%x' % target_addr)
    else:
        curAddr = idc.GetRegValue("EIP")
        print('Current instruction (0x%x) wrote to 0x%x' % (curAddr, target_addr))
    # why does the next instruction never return?
    #curAddr = idc.GetRegValue("EIP")
    #print('wroteToAddress currAddr is %x' % curAddr)

''' is test a subpart of the target register? '''
def isRegisterPart(target, test):
    if target == test:
        return True
    reg_letter = target[0]
    if target[0] == 'e':
        reg_letter = target[1]
    if test[0] == reg_letter:
        return True
    else:
        return False

def showSimicsMessage():
    global just_debug
    command = '@cgc.idaMessage()' 
    simics_string = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    print simics_string
    if 'Simics got lost' in simics_string:
        idc.Warning(simics_string)
    elif 'Just debug' in simics_string:
        just_debug = True
    return simics_string

       
def wroteToRegister(): 
    highlighted = idaapi.get_highlighted_identifier()
    if highlighted is None  or highlighted not in __regs:
       print('%s not in reg list' % highlighted)
       c=Choose([], "Run backward until selected register modified", 1)
       c.width=50
       c.list = __regs
       chose = c.choose()
       if chose == 0:
           print('user canceled')
           return
       else:
           highlighted = __regs[chose-1]
    print 'Looking for a write to %s...' % highlighted
    command = "@cgc.revToModReg('%s')" % highlighted
    simicsString = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    eip = gdbProt.getEIPWhenStopped(2)
    gdbProt.stepWait()
    curAddr = idc.GetRegValue("EIP")
    print('Current instruction (0x%x) wrote to reg %s' % (curAddr, highlighted))
    return eip
    
  
 
def chooseBookmark(): 
    global recent_bookmark
    c=Choose([], "select a bookmark", 1, deflt=recent_bookmark)
    c.width=50
    command = '@cgc.listBookmarks()'
    simicsString = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    #print lines
    lines = simicsString.split('\n')
    for l in lines:
        if ':' in l:
            #print l
            num, bm = l.split(':',1)
            c.list.append(bm.strip())
    chose = c.choose()
    if chose != 0:
        recent_bookmark = chose
        goToBookmarkRefresh(c.list[chose-1])
    else:
        print('user canceled')
     
def askGoToBookmark():
    mark = idc.AskStr('myBookmark', 'Name of bookmark to jump to:')
    if mark is not None and mark != 0:
        goToBookmarkRefresh(mark)


def highlightedBookmark(): 
    highlighted = idaapi.get_output_selected_text()
    if highlighted is not None:
        goToBookmarkRefresh(highlighted)

def listBookmarks():
    print('Bookmarks (highlight & alt-shift-b to go there)')
    command = '@cgc.listBookmarks()' 
    simicsString = gdbProt.Evalx('SendGDBMonitor("%s");' % command)
    print simicsString
    global bookmark_view
    bookmark_view.updateBookmarkView()
   
   
def goToBegin():
    '''
    NOT USED
    Send simics back to the earliest recorded eip 
    '''
    print('goToBegin')
    #simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.goToFirst()");') 
    #eip = getEIPWhenStopped()
    #stepWait()
    #runToUserSpace()
    goToBookmarkRefresh('_start+1')
    # trusting there is a first breakpoint
    #print('goToBegin got back from goToBookmarkRefresh now run to first break?')
    #GetDebuggerEvent(WFNE_SUSP | WFNE_CONT, -1)
    #GetDebuggerEvent(WFNE_SUSP | WFNE_CONT, -1)
    #print('back from goToBegin')

def goToBookmarkRefresh(mark):
    global bookmark_view
    bookmark_view.goToBookmarkRefresh(mark)

def goToOrigin():
    '''
    Send simics back to the eip where simics had stopped for debugging
    '''
    print('goToOrigin')
    bookmark_view.goToOrigin()
    #goToBookmarkRefresh('origin')

def setBreakAtStart():
    ''' keep from reversing past start of process '''
    addr = LocByName("_start")
    if addr is not None:
        bptEnabled = idc.CheckBpt(addr)
        if bptEnabled < 0:
    	    print('breakAtStart bpt set at 0x%x' % addr)
    	    idc.AddBpt(addr)
    else:
        print('setBreakAtStart, got no loc for _start')
    return addr

def goNowhere():
    '''
    Force ida to send server the current breakpoints
    '''
    #print('in goNowhere')
    #curAddr = idc.GetRegValue("EIP")
    #print('in goNowhere back from getReg')
    #bptEnabled, disabledSet = setAndDisable(curAddr)
    simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.skipAndMail()");') 
    eip = gdbProt.getEIPWhenStopped()
    gdbProt.stepWait()
    #print('goNowhere after stepInto')
    #GetDebuggerEvent(WFNE_SUSP | WFNE_CONT, -1)
    #reEnable(curAddr, bptEnabled, disabledSet)

def runToUserSpace():
    global bookmark_view
    bookmark_view.runToUserSpace()

def runToSyscall():
        simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.runToSyscall()");') 
        eip = gdbProt.getEIPWhenStopped(kernel_ok=True)
        print('runtoSyscall, stopped at eip 0x%x, now run to user space.' % eip)
        simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.runToUserSpace()");') 
        eip = gdbProt.getEIPWhenStopped()
        print('runtoSyscall, stopped at eip 0x%x, then stepwait.' % eip)
        gdbProt.stepWait()
        #print('runtoSyscall rev over')
        #doRevStepOver()
        #print('runtoSyscall done')

def revToSyscall():
        simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.revToSyscall()");') 
        eip = gdbProt.getEIPWhenStopped(kernel_ok=True)
        #print('revtoSyscall, stopped at eip 0x%x, now run to user space.' % eip)
        simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.runToUserSpace()");') 
        eip = gdbProt.getEIPWhenStopped()
        #print('revtoSyscall, stopped at eip 0x%x, then stepwait.' % eip)
        gdbProt.stepWait()
        print('revtoSyscall done')

def revBlock():
    cur_addr = idc.GetRegValue("EIP")
    f = idaapi.get_func(cur_addr)
    fc = idaapi.FlowChart(f)
    block_start = None
    prev_addr = None
    prev_block = None
    for block in fc:
        block_start = block.startEA
        print('block_start 0x%x, cur_addr is 0x%x' % (block_start, cur_addr))
        if block_start > cur_addr:
            break
        prev_addr = block_start
        prev_block = block

    if prev_addr == cur_addr:
        doRevStepInto()
    elif prev_addr is not None:
        next_addr = NextHead(prev_addr)
        if next_addr == cur_addr:
            ''' reverse two to get there? '''
            doRevStepInto()
            doRevStepInto()
        else:
            print('revBlock rev to 0x%x' % prev_addr)
            doRevToAddr(prev_addr, 1)
    else:
        print('must have been top, uncall')
        doRevFinish()
        

def testDialog():
    print("in testDialog")
    f = waitDialog.waitDialog()
    f.go()
    print("back from go")
    
# Ida does not believe their is a debugger until you do something, so break at current eip
def primePump():
    addr = setBreakAtStart()
    if addr is not None:
        goNowhere()

def rebuildBookmarkView():
    print 'rebuilding bookmark view'
    global bookmark_view
    bookmark_view.Create()
    bookmark_list = bookmark_view.updateBookmarkView()

def exitIda():
    simicsString = gdbProt.Evalx('SendGDBMonitor("@cgc.idaDone()");')
    print("Telling gdb server we are exiting")
    time.sleep(2)
    idaapi.qexit(0)

def doKeyMap():
    idaapi.CompileLine('static key_alt_shift_d() { RunPythonStatement("testDialog()"); }')
    AddHotkey("Alt+Shift+d", 'key_alt_shift_d')

    idaapi.CompileLine('static key_alt_f9() { RunPythonStatement("doReverse()"); }')
    AddHotkey("Alt+Shift+F9", 'key_alt_f9')
    idaapi.add_menu_item("Debugger/Attach to process", "^ Reverse continue process", "Alt+Shift+F9", 0, doReverse, None)
    
    idaapi.CompileLine('static key_alt_f8() { RunPythonStatement("doRevStepOver()"); }')
    AddHotkey("Alt+Shift+F8", 'key_alt_f8')
    idaapi.add_menu_item("Debugger/Run until return", "^ Rev step over", "Alt+Shift+F8", 0, doRevStepOver, None)
    
    idaapi.CompileLine('static key_alt_f7() { RunPythonStatement("doRevStepInto()"); }')
    AddHotkey("Alt+Shift+F7", 'key_alt_f7')
    idaapi.add_menu_item("Debugger/Step over", "^ Rev step into", "Alt-Shift-F7", 0, doRevStepInto, None)
    
    #idaapi.CompileLine('static key_alt_shift_f7() { RunPythonStatement("doRevStepInto()"); }')
    #AddHotkey("Alt+Shift+F7", 'key_alt_shift_f7')
    
    #idaapi.CompileLine('static key_alt_f7() { RunPythonStatement("doRevFinish()"); }')
    #AddHotkey("Alt+F7", 'key_alt_f7')
    idaapi.CompileLine('static key_alt_f6() { RunPythonStatement("doRevFinish()"); }')
    AddHotkey("Alt+F6", 'key_alt_f6')
    idaapi.add_menu_item("Debugger/Run to cursor", "^ Rev until call", "Alt+F6", 0, doRevFinish, None)
    
    idaapi.CompileLine('static key_alt_shift_f4() { RunPythonStatement("doRevToCursor()"); }')
    AddHotkey("Alt+Shift+F4", 'key_alt_shift_f4')
    idaapi.add_menu_item("Debugger/Run to cursor", "^ Rev to cursor", "Alt+Shift+F4", 1, doRevToCursor, None)
    
    idaapi.CompileLine('static key_alt_shift_s() { RunPythonStatement("wroteToSP()"); }')
    AddHotkey("Alt+Shift+s", 'key_alt_shift_s')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ Wrote to [ESP]", "Alt+Shift+s", 1, wroteToSP, None)
    
    idaapi.CompileLine('static key_alt_shift_a() { RunPythonStatement("wroteToAddressPrompt()"); }')
    AddHotkey("Alt+Shift+a", 'key_alt_shift_a')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ Wrote to address...", "Alt+Shift+a", 1, wroteToAddressPrompt, None)
    
    idaapi.CompileLine('static key_alt_shift_r() { RunPythonStatement("wroteToRegister()"); }')
    AddHotkey("Alt+Shift+r", 'key_alt_shift_r')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ Wrote to register...", "Alt+Shift+r", 1, wroteToRegister, None)
    
    idaapi.CompileLine('static key_alt_shift_m() { RunPythonStatement("showSimicsMessage()"); }')
    AddHotkey("Alt+Shift+m", 'key_alt_shift_m')
    
    idaapi.CompileLine('static key_alt_shift_o() { RunPythonStatement("goToOrigin()"); }')
    AddHotkey("Alt+Shift+o", 'key_alt_shift_o')
    
    idaapi.CompileLine('static key_alt_shift_t() { RunPythonStatement("goToBegin()"); }')
    AddHotkey("Alt+Shift+t", 'key_alt_shift_t')
    
    idaapi.CompileLine('static key_alt_shift_h() { RunPythonStatement("showHelp()"); }')
    AddHotkey("Alt+Shift+h", 'key_alt_shift_h')
    idaapi.add_menu_item("Help/Ida home page", "CGC Ida client help", "Alt+Shift+h", 0, showHelp, None)
    
    idaapi.CompileLine('static key_alt_shift_p() { RunPythonStatement("askSetBookmark()"); }')
    AddHotkey("Alt+Shift+p", 'key_alt_shift_p')
    
    idaapi.CompileLine('static key_alt_shift_j() { RunPythonStatement("chooseBookmark()"); }')
    AddHotkey("Alt+Shift+j", 'key_alt_shift_j')
    
    idaapi.CompileLine('static key_alt_shift_l() { RunPythonStatement("listBookmarks()"); }')
    AddHotkey("Alt+Shift+l", 'key_alt_shift_l')
    
    idaapi.CompileLine('static key_alt_shift_k() { RunPythonStatement("highlightedBookmark()"); }')
    AddHotkey("Alt+Shift+k", 'key_alt_shift_k')
    
    idaapi.CompileLine('static key_alt_shift_u() { RunPythonStatement("runToUserSpace()"); }')
    AddHotkey("Alt+Shift+u", 'key_alt_shift_u')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Run to user space", "Alt+Shift+u", 1, runToUserSpace, None)
    
    idaapi.CompileLine('static key_alt_c() { RunPythonStatement("runToSyscall()"); }')
    AddHotkey("Alt+c", 'key_alt_c')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Run to syscall", "Alt+c", 1, runToSyscall, None)
    
    idaapi.CompileLine('static key_alt_shift_c() { RunPythonStatement("revToSyscall()"); }')
    AddHotkey("Alt+Shift+c", 'key_alt_shift_c')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Run to syscall", "Alt+Shift+c", 1, revToSyscall, None)
    
    idaapi.CompileLine('static key_alt_shift_n() { RunPythonStatement("nameSysCalls()"); }')
    AddHotkey("Alt+Shift+n", 'key_alt_shift_n')
    
    idaapi.CompileLine('static key_alt_b() { RunPythonStatement("rebuildBookmarkView()"); }')
    AddHotkey("Alt+k", 'key_alt_b')
    idaapi.add_menu_item("View/Open subviews/Hex dump", "View bookmark window", "Alt+b", 1, rebuildBookmarkView, None)

    idaapi.CompileLine('static key_alt_shift_b() { RunPythonStatement("revBlock()"); }')
    AddHotkey("Alt+Shift+b", 'key_alt_shift_b')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Run to previous block", "Alt+Shift+b", 1, revBlock, None)
    
    idaapi.CompileLine('static key_alt_shift_q() { RunPythonStatement("exitIda()"); }')
    AddHotkey("Alt+Shift+q", 'key_alt_shift_q')
    idaapi.add_menu_item("Debugger/Terminate process", "Exit CGC Ida Client", "Alt+Shift+q", 1, exitIda, None)

def nameSysCalls(bail=False):
    print('in nameSysCalls assign names to sys calls')
    start = LocByName("_start")
    
    main = 0
    
    for x in XrefsFrom(start):
       if x.type == fl_CN:
          MakeNameEx(x.to, "main", 0)
          main = x.to
          break
    
    f = GetFunctionAttr(start, FUNCATTR_END)
    
    types = []
    
    types.append(ParseType("void __cdecl _terminate(int exitCode);", 0))
    types.append(ParseType("int __cdecl transmit(int fd, const void *buf, size_t count, size_t *tx_bytes);", 0))
    types.append(ParseType("int __cdecl receive(int fd, void *buf, size_t count, size_t *rx_bytes);", 0))
    types.append(ParseType("int __cdecl fdwait(int nfds, fd_set *readfds, fd_set *writefds, const struct timeval *timeout, int *readyfds);", 0))
    types.append(ParseType("int __cdecl allocate(size_t length, int is_X, void **addr);", 0))
    types.append(ParseType("int __cdecl deallocate(void *addr, size_t length);", 0))
    types.append(ParseType("int __cdecl random(void *buf, size_t count, size_t *rnd_bytes);", 0))

    comms = []
    comms.append("DECREE terminate")
    comms.append("DECREE transmit")
    comms.append("DECREE receive")
    comms.append("DECREE fdwait")
    comms.append("DECREE allocate")
    comms.append("DECREE deallocate")
    comms.append("DECREE random")
    
    names = ["_terminate", "transmit", "receive", "fdwait", "allocate", "deallocate", "random"]
    for i in range(7):
       if i == 1:
          f += 2
       MakeCode(f)
       MakeFunction(f, BADADDR)
       try:
           MakeNameEx(f, names[i], 0)
           ApplyType(f, types[i], 0)
       except:
           print('some trouble in MakeNameEx or ApplyType for %s, f is %d' % (names[i], f))
           pass
       end = GetFunctionAttr(f, FUNCATTR_END)
       got_int = False
       if (end - f) > 20000 and bail:
           print('function too big, 0x%x to 0x%x, skipping' % (f, end)) 
           continue
       while not got_int and f < end:
           f = NextAddr(f)
           if GetMnem(f) == "int":
               try:
                   MakeComm(f, comms[i]) 
               except:
                   pass
               got_int = True
       f = end
   
def checkHelp():
    pref_file = None
    if os.path.exists("prefs.txt"):
        pref_file = open("prefs.txt", 'r')
    if pref_file is None or "no_help" not in pref_file.read():
        if showHelp(True):
            print("user said don't show help at startup")
            if pref_file is not None:
                pref_file.close()
            pref_file = open("prefs.txt", 'a')
            pref_file.write("no_help")
            pref_file.close()
#Wait() 
primePump()
nameSysCalls(True)
print('back from nameSysCalls')
form=idaapi.find_tform("Stack view")
print('do switch')
idaapi.switchto_tform(form, True)
print('now create bookmark_view')
bookmark_view.Create()
bookmark_list = bookmark_view.updateBookmarkView()
for bm in bookmark_list:
    if 'nox' in bm:
        eip_str = bm.split(':')[1]
        eip = int(eip_str, 16)
        idc.MakeCode(eip) 

form=idaapi.find_tform("IDA View-EIP")
idaapi.switchto_tform(form, True)
# MakeCode(eip)
if not keymap_done:
    doKeyMap()
    print('dbg %r' % idaapi.dbg_is_loaded())

    showSimicsMessage()

    RefreshDebuggerMemory()
checkHelp()
showSimicsMessage()
if not just_debug:
    # first origin is sometimes off, call twice.
    #goToOrigin()
    goToOrigin()
Batch(0)
