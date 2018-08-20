# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
__all__ = ['prepare_vals']


def prepare_vals(values, to_write=False):
    if isinstance(values, dict):
        if set(values.keys()) <= set(['add', 'remove']):
            res = []
            if to_write:
                if 'add' in values.keys():
                    res.append(('create',
                            prepare_vals([v[1] for v in values['add']])))
                if 'remove' in values.keys():
                    res.append(('delete', values['remove']))
            else:
                # to create
                if 'add' in values.keys():
                    res = [x for _, x in values['add']]
        else:
            res = {}
            for key, value in values.items():
                if 'rec_name' in key or key == 'id':
                    continue
                value = prepare_vals(value)
                if value is not None:
                    res[key] = value
        return res or None
    elif isinstance(values, list):
        return [prepare_vals(v) for v in values]
    return values
