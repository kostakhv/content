from DockerHardeningCheck import check_memory, mem_size_to_bytes, check_pids, check_fd_limits, check_non_root


def test_check_memory():
    assert check_memory("10m")  # will return an error string


def test_mem_size():
    assert mem_size_to_bytes("1g") == (1024 * 1024 * 1024)
    assert mem_size_to_bytes("512m") == (512 * 1024 * 1024)


def test_pids():
    assert check_pids(10)


def test_fd_limits():
    assert check_fd_limits(100, 200)


def test_non_root():
    assert not check_non_root()  # we run tests as non root
