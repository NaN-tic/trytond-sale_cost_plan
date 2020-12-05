#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.pool import Pool
from . import production
from . import sale


def register():
    Pool.register(
        production.Production,
        sale.Plan,
        sale.SaleLine,
        module='sale_cost_plan', type_='model')
