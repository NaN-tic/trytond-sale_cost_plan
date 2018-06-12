# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction

from .tools import prepare_vals

__all__ = ['Sale', 'SaleLine', 'Plan',
    'ChangeLineQuantityStart', 'ChangeLineQuantity']
__metaclass__ = PoolMeta


class Sale:
    __name__ = 'sale.sale'
    productions = fields.Function(fields.One2Many('production', None,
        'Productions'), 'get_productions')

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls._error_messages.update({
                'missing_cost_plan': (
                    'Lines "%(lines)s" of sale "%(sale)s" doesn\'t have '
                    'Cost Plan, so it won\'t generate any production.'),
                })

    @classmethod
    def confirm(cls, sales):
        for sale in sales:
            missing_cost_plan = []
            for line in sale.lines:
                if (line.type == 'line' and line.product
                        and not getattr(line.product, 'purchasable', False)
                        and not line.cost_plan):
                    missing_cost_plan.append(line.product.rec_name)
            if missing_cost_plan:
                cls.raise_user_warning('missing_cost_plan%s' % sale.id,
                    'missing_cost_plan', {
                        'sale': sale.rec_name,
                        'lines': ', '.join(missing_cost_plan),
                        })
        super(Sale, cls).confirm(sales)

    @classmethod
    def process(cls, sales):
        for sale in sales:
            if sale.state in ('done', 'cancel'):
                continue
            with Transaction().set_user(0, set_context=True):
                sale.create_productions()
        super(Sale, cls).process(sales)

    def create_productions(self):
        productions = []
        for line in self.lines:
            productions += line.create_productions()
        return productions

    def get_productions(self, name):
        productions = []
        for line in self.lines:
            productions.extend([p.id for p in line.productions])
        return productions


class SaleLine:
    __name__ = 'sale.line'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        domain=[
            ('product', '=', Eval('product', 0)),
            ],
        states={
            'invisible': Eval('type') != 'line',
            },
        depends=['type', 'product'])
    productions = fields.One2Many('production', 'origin', 'Productions')

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

    def create_productions(self):
        pool = Pool()
        try:
            Operation = pool.get('production.operation')
        except KeyError:
            Operation = None

        if self.type != 'line' or self.quantity <= 0 or not self.cost_plan:
            return []
        if len(self.productions) > 0:
            return []

        productions = []
        for production_values in self.cost_plan.get_elegible_productions(
                self.unit, self.quantity):
            production = self.get_production(production_values)

            if production:
                if production.bom:
                    production.inputs = []
                    production.outputs = []
                    production.explode_bom()

                if getattr(production, 'route', None) and Operation:
                    production.operations = []
                    changes = production.update_operations()
                    for _, operation_vals in changes['operations']['add']:
                        operation_vals = prepare_vals(operation_vals)
                        production.operations.append(
                            Operation(**operation_vals))

                production.save()
                productions.append(production)
        return productions

    def get_production(self, values):
        pool = Pool()
        Production = pool.get('production')

        production = Production()
        production.company = self.sale.company
        production.warehouse = self.warehouse
        production.location = self.warehouse.production_location
        production.cost_plan = self.cost_plan
        production.origin = str(self)
        production.reference = self.sale.reference
        production.state = 'draft'
        production.product = values['product']
        production.quantity = values['quantity']
        production.uom = values.get('uom', production.product.default_uom)
        if hasattr(Production, 'stock_owner'):
            production.stock_owner = self.sale.party
        if (hasattr(Production, 'quality_template') and
                production.product.quality_template):
            production.quality_template = production.product.quality_template

        if 'process' in values:
            production.process = values['process']

        if 'route' in values:
            production.route = values['route']

        if 'bom' in values:
            production.bom = values['bom']
        return production

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['productions'] = None
        return super(SaleLine, cls).copy(lines, default=default)


class Plan:
    __name__ = 'product.cost.plan'

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls._error_messages.update({
                'cannot_create_productions_missing_bom': ('No production can '
                    'be created because Product Cost Plan "%s" has no BOM '
                    'assigned.')
                })

    def get_elegible_productions(self, unit, quantity):
        """
        Returns a list of dicts with the required data to create all the
        productions required for this plan
        """
        if not self.bom:
            self.raise_user_error('cannot_create_productions_missing_bom',
                self.rec_name)

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


class ChangeLineQuantityStart:
    __name__ = 'sale.change_line_quantity.start'

    def on_change_with_minimal_quantity(self):
        pool = Pool()
        Uom = pool.get('product.uom')

        minimal_quantity = super(ChangeLineQuantityStart,
            self).on_change_with_minimal_quantity()

        produced_quantity = 0
        productions = self.line.productions if self.line else []
        for production in productions:
            if production.state in ('assigned', 'running', 'done', 'cancel'):
                produced_quantity += Uom.compute_qty(production.uom,
                    production.quantity, self.line.unit)

        return max(minimal_quantity, produced_quantity)


class ChangeLineQuantity:
    __name__ = 'sale.change_line_quantity'

    @classmethod
    def __setup__(cls):
        super(ChangeLineQuantity, cls).__setup__()
        cls._error_messages.update({
                'quantity_already_produced': 'Quantity already produced!',
                'no_updateable_productions': ('There is no updateable '
                    'production available!'),
                })

    def transition_modify(self):
        line = self.start.line
        if (line.quantity != self.start.new_quantity
                and line.sale.state == 'processing'):
            self.update_production()
        return super(ChangeLineQuantity, self).transition_modify()

    def update_production(self):
        pool = Pool()
        Production = pool.get('production')
        Uom = pool.get('product.uom')

        line = self.start.line
        quantity = self.start.new_quantity

        for production in line.productions:
            if production.state in ('assigned', 'running', 'done', 'cancel'):
                quantity -= Uom.compute_qty(production.uom,
                    production.quantity, self.start.line.unit)
        if quantity < 0:
            self.raise_user_error('quantity_already_produced')

        updateable_productions = self.get_updateable_productions()
        if quantity >= line.unit.rounding:
            production = updateable_productions.pop(0)
            self._change_production_quantity(
                production,
                Uom.compute_qty(line.unit, quantity, production.uom))
            production.save()
        if updateable_productions:
            Production.delete(updateable_productions)

    def _change_production_quantity(self, production, quantity):
        pool = Pool()
        Operation = None
        try:
            Operation = pool.get('production.operation')
        except KeyError:
            pass

        production.quantity = quantity
        if getattr(production, 'route', None):
            changes = production.update_operations()
            if changes and changes.get('operations'):
                if changes['operations'].get('remove'):
                    Operation.delete([
                            Operation(o)
                            for o in changes['operations']['remove']])
                production.operations = []
                for _, operation_vals in changes['operations']['add']:
                    operation_vals = prepare_vals(operation_vals)
                    production.operations.append(Operation(**operation_vals))
        if production.bom:
            production.inputs = []
            production.outputs = []
            production.explode_bom()
        production.save()

    def get_updateable_productions(self):
        productions = sorted(
            [p for p in self.start.line.productions
                if p.state in ('draft', 'waiting')],
            key=self._production_key)
        if not productions:
            self.raise_user_error('no_updateable_productions')
        return productions

    def _production_key(self, production):
        return -production.quantity
