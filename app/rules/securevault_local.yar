/* Local educational detection rules. These are indicators, not a complete AV signature set. */

rule EICAR_Antivirus_Test_File
{
    meta:
        description = "Recognizes the harmless EICAR antivirus test fixture"
        category = "test-signature"
    strings:
        $eicar = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*" ascii
    condition:
        $eicar
}

rule PowerShell_Encoded_Command
{
    meta:
        description = "Flags a script combining PowerShell encoded-command switches with encoded payload indicators"
        category = "suspicious-script"
    strings:
        $switch1 = "-EncodedCommand" nocase ascii
        $switch2 = "-enc " nocase ascii
        $decode1 = "FromBase64String" nocase ascii
        $decode2 = "[Convert]::FromBase64String" nocase ascii
    condition:
        any of ($switch*) and any of ($decode*)
}

rule JavaScript_Dynamic_Decode_And_Execution
{
    meta:
        description = "Flags JavaScript containing both base64 decoding and dynamic code execution primitives"
        category = "suspicious-script"
    strings:
        $decode1 = "atob(" nocase ascii
        $decode2 = "Buffer.from(" nocase ascii
        $exec1 = "eval(" nocase ascii
        $exec2 = "new Function(" nocase ascii
    condition:
        any of ($decode*) and any of ($exec*)
}

rule Office_AutoOpen_And_Shell_Execution
{
    meta:
        description = "Flags Office macro source containing an auto-run entry and shell launch"
        category = "suspicious-macro-source"
    strings:
        $auto1 = "AutoOpen" nocase ascii
        $auto2 = "Document_Open" nocase ascii
        $shell1 = "Shell(" nocase ascii
        $shell2 = "WScript.Shell" nocase ascii
    condition:
        any of ($auto*) and any of ($shell*)
}

rule SecureVault_Training_Marker
{
    meta:
        description = "Harmless fixture used to explain a custom local signature match"
        category = "training"
    strings:
        $marker = "SECUREVAULT-DEMO-SIGNATURE-MATCH" ascii
    condition:
        $marker
}
