from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from datetime import date, timedelta, datetime, time


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    maintenance_request_line_ids = fields.One2many(
        comodel_name="maintenance.request.line",
        inverse_name="maintenance_request_id",
    )

    check_maintenance_plan = fields.Boolean(string="etch_maintenance_plan",
                                            default=False,
                                            help="check Equipment if need  maintenance plan")

    orders_spare_parts = fields.Boolean(default=False)

    equipment_consumption = fields.Integer(string="Consumption", required=False, )

    type_of_maintenance = fields.Selection(
        related="equipment_id.type_of_maintenance",
        string="Maintenance Type", )

    expected_mtbf = fields.Integer(
        related="equipment_id.expected_mtbf",
        string="Expected Mean Time Between Failure", )

    tasks = fields.Text(
        string="Tasks",
        required=False, )

























    def action_go_validate_spare_part(self):

        line_ids = [
            (0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.quantity,
            })
            for line in self.maintenance_request_line_ids
            if line.product_id  # تجاهل الصفوف الفاضية
        ]

        return {
            'type': 'ir.actions.act_window',
            'name': 'Select Spare Parts',
            'res_model': 'validate.spare.part.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maintenance_request_id': self.id,
                'default_line_ids': line_ids,
            }
        }


    # Def to check if system need to make  Maintenance Request Preventive


    @api.model
    def maintenance_request_plans(self):
        today = fields.Date.today()
        # in case (if maintenance done is True)
        # in case (if Type stage at maintenance need Maintenance after that [stage_id.no_maintenance == False])
        # in case (if system don't check maintenance plan before that [check_maintenance_plan = False])
        # in case (Type of maintenance is preventive [maintenance_type = preventive])
        # in case (if in maintenance has an equipment [equipment_id != False])
        target_domain = [
            ('done', '=', True),
            ('stage_id.no_maintenance', '=', False),
            ('check_maintenance_plan', '=', False),
            ('maintenance_type', '=', "preventive"),
            ('equipment_id', '!=', False),

        ]
        # all records in case
        records_to_update = self.search(target_domain)

        if not records_to_update:
            return True




        def future_request_exists(task_name, equipment_id):
            return self.search_count([
                ('name', '=', task_name),
                ('equipment_id', '=', equipment_id),
                ('request_date', '>=', today),
                ('maintenance_type', '=', 'preventive'),
                ('done', '=', False),
            ]) > 0



        for request in records_to_update:
            request.check_maintenance_plan = True

            sorted_plans = request.equipment_id.maintenance_equipment_plan_ids.sorted(
                key = lambda p: (p.done, p.in_case)
            )


            for plan in sorted_plans:

                if plan.done :
                    continue


                elif not plan.done and plan.in_case_unit:


                    if plan.in_case <= request.equipment_consumption:
                        scheduled_dt = datetime.combine(today, time(9, 0, 0))

                        if plan.in_case_unit in ['kilometers']:

                            if future_request_exists(plan.tasks, request.equipment_id.id):
                                continue

                            else:
                                self.create({
                                    'name': plan.tasks,
                                    'equipment_id': request.equipment_id.id,
                                    'maintenance_type': 'preventive',
                                    'user_id': request.user_id.id,
                                    'duration': 1.0,
                                    'schedule_date': scheduled_dt,
                                    'equipment_consumption': request.equipment_consumption,
                                    'request_date': today,
                                })
                                plan.done = True
                            break

                        else:

                            time_in_days = None
                            if plan.in_case_unit == 'hours':
                                time_in_days = plan.in_case / 8
                            elif plan.in_case_unit == 'days':
                                time_in_days = plan.in_case
                            elif plan.in_case_unit == 'weeks':
                                time_in_days = plan.in_case * 7
                            elif plan.in_case_unit == 'years':
                                time_in_days = plan.in_case * 365

                            if time_in_days is not None:
                                the_day = today + timedelta(days=time_in_days)

                                scheduled_dt = datetime.combine(the_day, time(9, 0, 0))
                                if future_request_exists(plan.tasks, request.equipment_id.id):
                                    continue
                                else:

                                    self.create({
                                        'name': plan.tasks,
                                        'equipment_id': request.equipment_id.id,
                                        'maintenance_type': 'preventive',
                                        'equipment_consumption': request.equipment_consumption,
                                        'request_date': the_day,
                                        'schedule_date': scheduled_dt,
                                        'duration': 1.0,
                                        'user_id': request.user_id.id,
                                    })
                                    plan.done = True
                                    break
                            else:
                                continue

                    else:
                        continue
        return True





class MaintenanceRequestLines(models.Model):
    _name = 'maintenance.request.line'
    _description = 'Maintenance Request Line'

    maintenance_request_id = fields.Many2one(
        comodel_name="maintenance.request",
        string="Maintenance Request",
    )

    done = fields.Boolean(default=False, readonly=True)

    wizard_id = fields.Many2one(
        comodel_name="validate.spare.part.wizard",
    )

    product_id = fields.Many2one('product.template', string="Product", domain=[('spare_parts_ok', '=', True)], )
    quantity = fields.Float(string="Quantity", default=1.0)
    qty_available = fields.Float(
        'On Hand', compute='_compute_qty_available', )

    difference = fields.Float(
        string='After Consumption',
        compute='_compute_difference',
    )

    @api.depends('product_id', 'quantity')
    def _compute_qty_available(self):
        for line in self:
            line.qty_available = line.product_id.qty_available if line.product_id else 0.0

    @api.depends('product_id', 'quantity')
    def _compute_difference(self):
        for line in self:
            line.difference = line.qty_available - line.quantity if line.quantity and line.qty_available else 0.0

    @api.constrains('quantity', 'qty_available')
    def _check_quantity(self):
        for line in self:

            if line.qty_available == 0:
                raise ValueError("in page Orders Spare Parts \n  you don't have stock.")
            if line.qty_available < 0:
                raise ValueError("in page Orders Spare Parts \n  stock must be a positive number.")
            if line.quantity <= 0:
                raise ValidationError("in page Orders Spare Parts \n  Quantity must be a positive number.")

            if line.quantity > line.qty_available:
                raise ValidationError("in page Orders Spare Parts \n  Quantity must be under vals of stock.")



