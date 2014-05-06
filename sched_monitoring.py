# -*- encoding: utf-8 -*-
##############################################################################
#
#    res_partner
#    Copyright (c) 2013 Codeback Software S.L. (http://codeback.es)    
#    @author: Miguel García <miguel@codeback.es>
#    @author: Javier Fuentes <javier@codeback.es>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import fields, osv
from datetime import datetime, timedelta
from openerp.tools.translate import _

import pytz
import pdb

class mrp_sched_monitoring(osv.osv):
        
    _name = "mrp.sched.monitoring"

    def _compute_efficiency(self, cr, uid, ids, field_names, arg, context=None):
        vals={}
        for day in self.browse(cr,uid,ids, context):
            vals[day.id] = {}
            vals[day.id]["efficiency"] = day.production_hours / day.scheduled_hours * 100
            vals[day.id]["ref_efficiency"] = day.ref_production_hours / day.scheduled_hours * 100
            if vals[day.id]["efficiency"] <= 50.0:
                vals[day.id]["efficiency_level"] = "Eficiencia muy baja"
            elif vals[day.id]["efficiency"] > 50.0 and vals[day.id]["efficiency"] <= 75.0:
                vals[day.id]["efficiency_level"] = "Eficiencia baja"
            elif vals[day.id]["efficiency"] > 75.0 and vals[day.id]["efficiency"] <= 90.0:
                vals[day.id]["efficiency_level"] = "Eficiencia media"
            elif vals[day.id]["efficiency"] > 90.0 and vals[day.id]["efficiency"] <= 100.0:
                vals[day.id]["efficiency_level"] = "Eficiencia alta"
            else:
                vals[day.id]["efficiency_level"] = "Eficiencia muy alta"

        return vals

    _columns = {   
        'day': fields.date('Work day', readonly=True),
        'production_hours': fields.float('Horas trabajadas', readonly=True),
        'ref_production_hours': fields.float('Horas de referencia', readonly=True),
        'scheduled_hours': fields.float('Horas planificadas', readonly=True),
        'efficiency': fields.function(_compute_efficiency, type='float', string='Efficiency (%)', multi='compute_efficiency'),
        'ref_efficiency': fields.function(_compute_efficiency, type='float', string='Ref. Efficiency (%)', multi='compute_efficiency'),
        'efficiency_level': fields.function(_compute_efficiency, type='char', string='Efficiency Level', multi='compute_efficiency'),
    }

    def run_monitoring(self, cr, uid, start_date=None, end_date=datetime.now(), context=None):

        work_sched_model = self.pool.get('resource.calendar')
        work_sched_ids = work_sched_model.search(cr, uid, [("name", "=", "Fábrica")])
                       
        if len(work_sched_ids) > 0:
            work_sched = work_sched_model.browse(cr, uid, work_sched_ids)[0]                                    

            if start_date == None:
                start_date = datetime.today() + timedelta(days=-7)
            
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            
            production_days = self._get_production_days(cr, uid, start_date, end_date)

            # Clear days
            self._remove_days(cr, uid, start_date, end_date, context=context)

            # Create new days
            for date, value in production_days.iteritems(): 

                week_day = date.isocalendar()[2]
                scheduled_hours = work_sched.attendance_ids[week_day-1].hour_to - work_sched.attendance_ids[week_day-1].hour_from

                record = {
                    'day': date,
                    'production_hours': value['hours'],
                    'ref_production_hours': value['ref_hours'],
                    'scheduled_hours': scheduled_hours,
                }
                self.create(cr, uid, record, context=context)

    def _get_production_days(self, cr, uid, start_date, end_date):

        str_start_date = datetime.strftime(start_date, '%Y-%m-%d %H:%M:%S')
        str_end_date = datetime.strftime(end_date, '%Y-%m-%d %H:%M:%S')
        
        args = [('date_planned', '>=', str_start_date), ('date_planned', '<', str_end_date), ('state', '=', "done")]
        
        production_model = self.pool.get('mrp.production')
        productions_ids = production_model.search(cr, uid, args, order='date_planned asc')
        productions = production_model.browse(cr, uid, productions_ids)

        production_days = {}
        # pdb.set_trace()
        for production in productions:            
            date = datetime.strptime(production.date_planned, '%Y-%m-%d %H:%M:%S').date()
            production_days.setdefault(date, {})
            production_days[date].setdefault("hours", 0.0)
            production_days[date].setdefault("ref_hours", 0.0)
            production_days[date]["hours"] += production.hour_total
            line = production.routing_id.workcenter_lines[0]
            production_days[date]["ref_hours"] += line.ref_hour_nbr * production.product_qty

        return production_days

    def _remove_days(self, cr, uid, start_date, end_date, context=None):

        start_date = start_date.date()
        end_date = end_date.date()
        
        str_start_date = datetime.strftime(start_date, '%Y-%m-%d')
        str_end_date = datetime.strftime(end_date, '%Y-%m-%d')
        
        args = [('day', '>=', str_start_date), ('day', '<', str_end_date)]
        ids = self.search(cr, uid, args)
        self.unlink(cr, uid, ids, context=context)

class mrp_sched_monitoring_runner(osv.osv_memory):
    _name = "mrp.sched.monitoring.runner"
    _columns = {
        'start_date': fields.datetime('Start Date', required=True),
        'end_date': fields.datetime('End Date', required=True)        
    } 
    
    _defaults = {
        'start_date' : datetime.strftime(datetime.now() + timedelta(days=-7) , '%Y-%m-%d %H:%M:%S'),
        'end_date': datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'),
    }

    def run_monitoring(self, cr, uid, ids, context=None):
        
        obj = self.pool.get('mrp.sched.monitoring')
        data = self.browse(cr, uid, ids, context=context)[0]      

        start_date = datetime.strptime(data.start_date, '%Y-%m-%d %H:%M:%S')
        end_date = datetime.strptime(data.end_date, '%Y-%m-%d %H:%M:%S')

        obj.run_monitoring(cr, uid, start_date=start_date, end_date=end_date, context=context)
        
        menu_mod = self.pool.get('ir.ui.menu')        
        args = [('name', '=', 'MRP Sched Monitoring')]
        menu_ids = menu_mod.search(cr, uid, args)
        
        return {
            'name': 'MRP Sched Monitoring',
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {'menu_id': menu_ids[0]},
        }      