CLUSTER_CONFIG = {
    "nodes":  [
        {
            "name": "node-1",
            "id": "ea76306b",
            "port_number": 10,
            "ip": "192.168.1.23",
            "model": "RPI3B+",
            "label": ""
        }
    ],
    "switch": {
        "address": "192.168.1.24",
        "username": b"admin",
        "password": b"seduce"
    },
    "environments": [
        {
            "name": "raspbian",
            "absolute_path": "/nfs/raspi1/environments/2018-11-13-raspbian-stretch-lite.zip",
            "nfs_path": "/environments/2018-11-13-raspbian-stretch-lite.zip"
        }
    ]
}