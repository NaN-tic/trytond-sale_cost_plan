# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = ['Production']
__metaclass__ = PoolMeta


class Production:
    __name__ = 'production'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        states={
            'readonly': ~Eval('state').in_(['request', 'draft']),
            },
        depends=['state'])
