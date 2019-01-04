# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard

__all__ = ['Production']


class Production(metaclass=PoolMeta):
    __name__ = 'production'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        states={
            'readonly': ~Eval('state').in_(['request', 'draft']),
            },
        depends=['state'])

