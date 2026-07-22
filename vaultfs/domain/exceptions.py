class VaultFSError(Exception): ...


class PermissionDeniedError(VaultFSError):
    def __init__(self, node_id: int, principal: str = "") -> None:
        self.node_id = node_id
        self.principal = principal
        super().__init__(f"Permission denied for node {node_id}")


class DirectoryNotEmptyError(VaultFSError):
    def __init__(self, node_id: int) -> None:
        self.node_id = node_id
        super().__init__(f"Directory {node_id} is not empty")
