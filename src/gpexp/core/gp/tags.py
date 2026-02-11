"""GlobalPlatform TLV tags for GET STATUS responses."""

GP_AID = 0x4F
GP_LIFECYCLE = 0x9F70
GP_PRIVILEGES = 0xC5
GP_EXECUTABLE_MODULE_AID = 0x84

GP_TAG_NAMES: dict[int, str] = {
    GP_AID: "AID",
    GP_LIFECYCLE: "Lifecycle State",
    GP_PRIVILEGES: "Privileges",
    GP_EXECUTABLE_MODULE_AID: "Executable Module AID",
}
