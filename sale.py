# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError

from .tools import prepare_vals

__all__ = ['SaleLine', 'Plan']

class SaleLine(metaclass=PoolMeta):
    __name__ = 'sale.line'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        domain=[
            ('product', '=', Eval('product', 0)),
            ],
        states={
            'invisible': Eval('type') != 'line',
            },
        depends=['type', 'product'])

    @fields.depends('cost_plan', 'product')
    def on_change_product(self):
        CostPlan = Pool().get('product.cost.plan')
        plan = None
        if self.product:
            plans = CostPlan.search([('product', '=', self.product.id)],
                order=[('number', 'DESC')], limit=1)
            if plans:
                plan = plans[0]
                self.cost_plan = plan
        super(SaleLine, self).on_change_product()
        if plan:
            self.cost_plan = plan

class Plan(metaclass=PoolMeta):
    __name__ = 'product.cost.plan'

    def get_elegible_productions(self, unit, quantity):
        """
        Returns a list of dicts with the required data to create all the
        productions required for this plan
        """
        if not self.bom:
            raise UserError(gettext(
                'sale_cost_plan.cannot_create_productions_missing_bom',
                plan=self.rec_name))

        prod = {
            'product': self.product,
            'bom': self.bom,
            'uom': unit,
            'quantity': quantity,
            }
        if hasattr(self, 'route'):
            prod['route'] = self.route
        if hasattr(self, 'process'):
            prod['process'] = self.process

        res = [
            prod
            ]
        res.extend(self._get_chained_productions(self.product, self.bom,
                quantity, unit))
        return res

    def _get_chained_productions(self, product, bom, quantity, unit,
            plan_boms=None):
        "Returns base values for chained productions"
        pool = Pool()
        Input = pool.get('production.bom.input')

        if plan_boms is None:
            plan_boms = {}
            for plan_bom in self.boms:
                if plan_bom.bom:
                    plan_boms[plan_bom.product.id] = plan_bom

        factor = bom.compute_factor(product, quantity, unit)
        res = []
        for input_ in bom.inputs:
            input_product = input_.product
            if input_product.id in plan_boms:
                # Create production for current product
                plan_bom = plan_boms[input_product.id]
                prod = {
                    'product': plan_bom.product,
                    'bom': plan_bom.bom,
                    'uom': input_.uom,
                    'quantity': Input.compute_quantity(input_, factor),
                    }
                res.append(prod)
                # Search for more chained productions
                res.extend(self._get_chained_productions(input_product,
                        plan_bom.bom, quantity, input_.uom, plan_boms))
        return res
