import pathlib

p = pathlib.Path(r'C:\Users\anasa\tasker-github\backend\hands_knowledge\_seg\maps_p04.md')
t = p.read_text(encoding='utf-8')
anchor = 'far more robust than parsing bytes.'
i = t.rfind(anchor)
assert i > 0
closing = (
    " TargetPath is resolved by the link parser on the machine reading it, so a link built"
    " for a drive letter that later remaps can come back pointing somewhere else; pin verifiable"
    " presence by IDList forms only when necessary. Extra data blocks on the same link carry"
    ' the elevation flag ("Run as administrator" = default verb becomes `runas`, so `Start-Process`'
    ' on the .lnk can raise UAC and hand off is required per unclimbable-walls rules); WScript.Shell'
    ' cannot write that flag \u2014 set it through `IShellLinkDataList`/`IPersistFile` from a compiled'
    ' helper, or accept the prompt in the automation flow. Downloaded shortcuts may carry the'
    ' Zone.Identifier stream: read with `Get-Content file.lnk -Stream Zone.Identifier`, clear'
    ' with `Unblock-File`.'
)
t = t[:i] + closing + '\n'
p.write_text(t, encoding='utf-8', newline='\n')
print('fixed, %d bytes' % len(t.encode('utf-8')))
