"""ISO 7816-4 common TLV tags."""

# FCI (File Control Information)
FCI_TEMPLATE = 0x6F
DF_NAME = 0x84
FCI_PROPRIETARY = 0xA5

# FCP (File Control Parameters)
FCP_TEMPLATE = 0x62
FILE_SIZE = 0x80
TOTAL_FILE_SIZE = 0x81
FILE_DESCRIPTOR = 0x82
FILE_ID = 0x83
SHORT_FILE_ID = 0x88
LIFE_CYCLE_STATUS = 0x8A
SECURITY_ATTRIBUTES = 0x86

TAG_NAMES: dict[int, str] = {
    FCI_TEMPLATE: "FCI Template",
    DF_NAME: "DF Name",
    FCI_PROPRIETARY: "FCI Proprietary Template",
    FCP_TEMPLATE: "FCP Template",
    FILE_SIZE: "File Size",
    TOTAL_FILE_SIZE: "Total File Size",
    FILE_DESCRIPTOR: "File Descriptor",
    FILE_ID: "File Identifier",
    SHORT_FILE_ID: "Short File Identifier",
    LIFE_CYCLE_STATUS: "Life Cycle Status",
    SECURITY_ATTRIBUTES: "Security Attributes",
}
