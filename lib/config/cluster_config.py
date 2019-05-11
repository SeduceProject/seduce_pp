CLUSTER_CONFIG = {
    "controller": {
        "ip": "192.168.1.22",
        "public_key": """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDDjXBuWj8MJuGcJDx1/ch7nDBptyoXjBP3DNQPel+A+sI/76dT/MPw6HgUxywb0aJ1L50QU0xDU/dhl0er4WK31DLf6QR2ursZ7yYhgrRm8uugYEIYxs8qu5SyNXiNPOTnH+Pd+IUt/T3iqyrPLOifnuqWaeN26WqUlWiAcqIrJdfl+KgNuYOS4u3bFNEPBuab3wqi8JREkv25j9NJ7UMrVUzhQ8eMeCQmQsoVBsMwfhLZ/DyZz4o/+IsP05AmJs0q3eJJwsFSWerZTNtes97qkD/H+RQv5VhGqYKncyCoFHt0D4lstFizlG/1rxow6scssQR2dfs1XSuc6VHCnuLv root@nuc1"""
    },
    "nodes":  [
        {
            "name": "node-1",
            "id": "ea76306b",
            "port_number": 1,
            "ip": "192.168.1.51",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-2",
            "id": "071f11f3",
            "port_number": 2,
            "ip": "192.168.1.52",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-3",
            "id": "1c2085b9",
            "port_number": 3,
            "ip": "192.168.1.53",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-4",
            "id": "4fb9704c",
            "port_number": 4,
            "ip": "192.168.1.54",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-5",
            "id": "091a30c2",
            "port_number": 5,
            "ip": "192.168.1.55",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-6",
            "id": "ebe8629c",
            "port_number": 6,
            "ip": "192.168.1.56",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-7",
            "id": "2ebf44b1",
            "port_number": 7,
            "ip": "192.168.1.57",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-8",
            "id": "23ff05a5",
            "port_number": 8,
            "ip": "192.168.1.58",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-9",
            "id": "6fa8f83c",
            "port_number": 9,
            "ip": "192.168.1.59",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-10",
            "id": "5e8fa6a1",
            "port_number": 10,
            "ip": "192.168.1.60",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-11",
            "id": "a67c64be",
            "port_number": 11,
            "ip": "192.168.1.61",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-12",
            "id": "1760325b",
            "port_number": 12,
            "ip": "192.168.1.62",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-13",
            "id": "dd5cfc3a",
            "port_number": 13,
            "ip": "192.168.1.63",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-14",
            "id": "0a1c5d6c",
            "port_number": 14,
            "ip": "192.168.1.64",
            "model": "RPI3B+",
            "label": ""
        }
    ],
    "switch": {
        "address": "192.168.1.1",
        "username": b"admin",
        "password": b"seduce"
    },
    "environments": [
        {
            "name": "raspbian",
            "absolute_path": "/nfs/raspi1/environments/2018-11-13-raspbian-stretch-lite.zip",
            "nfs_path": "/environments/2018-11-13-raspbian-stretch-lite.zip"
        },
        {
            "name": "raspbian_new",
            "absolute_path": "/nfs/raspi1/environments/image_2019-04-27-Raspbian-lite.zip",
            "nfs_path": "/environments/image_2019-04-27-Raspbian-lite.zip"
        },
        {
            "name": "raspbian_cloud9",
            "absolute_path": "/nfs/raspi1/environments/image_2019-05-05-Raspbian_Cloud9-lite.zip",
            "nfs_path": "/environments/image_2019-05-05-Raspbian_Cloud9-lite.zip"
        }
    ]
}
