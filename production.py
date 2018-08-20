# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard

__all__ = ['Production', 'ChangeQuantityStart', 'ChangeQuantity']


class Production(metaclass=PoolMeta):
    __name__ = 'production'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        states={
            'readonly': ~Eval('state').in_(['request', 'draft']),
            },
        depends=['state'])

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        origins = super(Production, cls)._get_origin()
        origins.append('sale.line')
        return origins


class ChangeQuantityStart(ModelView):
    'Change Production Quantity - Start'
    __name__ = 'production.change_quantity.start'

    production = fields.Many2One('production', 'Production', readonly=True)
    sale_line = fields.Many2One('sale.line', 'Sale Line', readonly=True)
    current_quantity = fields.Float('Current Quantity',
        digits=(16, Eval('unit_digits', 2)), readonly=True,
        depends=['unit_digits'])
    new_quantity = fields.Float('New Quantity',
        digits=(16, Eval('unit_digits', 2)), required=True,
        domain=[
            ('new_quantity', '!=', Eval('current_quantity')),
            ('new_quantity', '>', 0),
            ],
        depends=['unit_digits', 'current_quantity'])
    uom = fields.Many2One('product.uom', 'Uom', readonly=True)
    unit_digits = fields.Integer('Unit Digits', readonly=True)


class ChangeQuantity(Wizard):
    'Change Production Quantity'
    __name__ = 'production.change_quantity'

    start = StateView('production.change_quantity.start',
        'sale_cost_plan.production_change_quantity_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Modify', 'modify', 'tryton-ok', default=True),
            ])
    modify = StateTransition()

    @classmethod
    def __setup__(cls):
        super(ChangeQuantity, cls).__setup__()
        cls._error_messages.update({
                'invalid_production_state': (
                    'You cannot modify the quantity of Production "%s" '
                    'because it is not in state "Draft" or "Waiting".'),
                'production_no_related_to_sale': (
                    'The Production "%s" is not related to any sale.\n'
                    'In this case, you can\'t use this wizard but you can '
                    'modify the quantity directly in production\'s form.'),
                })

    def default_start(self, fields):
        pool = Pool()
        Production = pool.get('production')
        SaleLine = Pool().get('sale.line')

        production = Production(Transaction().context['active_id'])
        if production.state not in ('draft', 'waiting'):
            self.raise_user_error('invalid_production_state',
                production.rec_name)
        if not isinstance(production.origin, SaleLine):
            self.raise_user_error('production_no_related_to_sale')
        return {
            'production': production.id,
            'sale_line': production.origin.id,
            'current_quantity': production.quantity,
            'uom': production.uom.id,
            'unit_digits': production.uom.digits,
            }

    def transition_modify(self):
        pool = Pool()
        Uom = pool.get('product.uom')
        SaleChangeLineQuantity = pool.get('sale.change_line_quantity',
            type='wizard')

        sale_line = self.start.sale_line
        sale_line_new_quantity = (sale_line.quantity
            + Uom.compute_qty(
                self.start.uom,
                self.start.new_quantity - self.start.current_quantity,
                sale_line.unit))

        sale_change_quantity = SaleChangeLineQuantity(self._session_id)
        sale_change_quantity.start.sale = sale_line.sale
        sale_change_quantity.start.line = sale_line
        sale_change_quantity.start.current_quantity = sale_line.quantity
        sale_change_quantity.start.new_quantity = sale_line_new_quantity
        sale_change_quantity.start.unit = sale_line.unit
        sale_change_quantity.start.unit_digits = sale_line.unit.digits
        sale_change_quantity.transition_modify()
        return 'end'
