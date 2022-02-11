import yaml

with open('temp/_bands.yml') as f:
    data = yaml.load(f, yaml.Loader)

with open('temp/bands.yml', 'w') as f:
    yaml.dump(
        {
            k: {
                _k: ([i / 40 for i in _v] if isinstance(_v, list) else _v)
                for _k, _v in v.items()
            }
            for k, v in data.items()
        },
        f,
    )
