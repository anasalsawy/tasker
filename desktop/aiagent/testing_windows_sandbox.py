import winsandbox

def main():
    sandbox = winsandbox.new_sandbox()
    sandbox.rpyc.modules.subprocess.run('explorer .')


if __name__ == '__main__':
    main()
