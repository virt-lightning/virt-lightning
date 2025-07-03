class Userdata:
    """
    Class to represent user data for a virtual machine.
    This class is used to store and manage user data that can be passed to the VM.
    """

    def __init__(self, **kwargs):
        """
        Initialize the Userdata instance with the provided userdata string.

        :param userdata: The user data string to be stored.
        """
        self.resize_rootfs = True
        self.disable_root = 0
        self.bootcmd = []
        self.runcmd = []

    def __str__(self):
        """
        Return the string representation of the Userdata instance.

        :return: The user data string.
        """
        attrs = vars(self)
        return "\n".join(f"{k}: {v}" for k, v in attrs.items())
    

    @root_password.setter
    def root_password(self, value):
        self.disable_root = False
        self.password = value
        self.chpasswd = {
            "list": f"root:{value}\n",
            "expire": False,
        }
        self.ssh_pwauth = True
        self.record_metadata("root_password", value)