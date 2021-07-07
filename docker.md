# docker usage

## build

to build the image from the dockerfile (which is basically a development version) run the following command:

```bash
docker build --tag monai-dev .
```

## running a container

to run the container, use the following command:

```bash
docker run -it \ # run an interactive shell session
    -p 8888:8888 \ # maps jupyter port
    -v <host code dir>:/opt/monai/<container code dir> \ # maps host directory code directory to container
    -v <host data dir>:/opt/monai/<container data dir> \ # maps host directory data directory to container
    --gpus all \ # make all gpus available to the docker container
    --shm-size <int>G \ # increases the shared memory size by <int> gigabytes
    monai-dev:latest
```

You can map additional ports as needed (such as 6000 for tensorboard) using the `-p` flag. Same goes for additional volumes as needed with the `-v` flag. The shell will print the link where you can access jupyter running inside the container.

## other

highly recommend running [portainer](https://www.portainer.io/) to monitor/troubleshoot the `monai-dev` and other containers.
