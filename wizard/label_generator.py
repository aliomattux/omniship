from openerp.osv import osv, fields


class OmnishipProcessor(osv.osv_memory):
    _name = 'omniship.processor'
    _columns = {
        'declared_value': fields.float('Declared Value'),
	'delivery_method': fields.many2one('delivery.carrier', 'Delivery Method', domain="[('service', '!=', False)]"),
	'return_label': fields.boolean('Return Label'),
	'alternate_sender_address': fields.many2one('res.partner', 'Alternate Sender Address'),
	'recipient_address': fields.many2one('res.partner', 'Recipient Address'),
        'weight': fields.float('Package Weight'),
        'length': fields.float('Length'),
        'width': fields.float('Width'),
	'carrier': fields.char('Carrier'),
	'customs_tab': fields.boolean('Requires Custom Forms'),
        'height': fields.float('Height'),
        'label_sub_type': fields.selection([
                ('None', 'None'),
                ('Integrated', 'Integrated')
        ], 'Label Sub Type'),
        'integrated_form_type': fields.selection([
                ('Form2976', 'Form2976(Same as CN22)'),
                ('Form2976A', 'Form2976A(Same as CP72)'),
        ], 'Form Type'),
        'shape_dimension': fields.many2one('delivery.box.shape',
            'Box Shape/Dimensions'),
	'include_postage': fields.boolean('Include Postage'),
    }

    _defaults = {
	'weight': 1.0,
    }


    def default_get(self, cr, uid, fields, context=None):
        if context is None: context = {}
        res = super(OmnishipProcessor, self).default_get(cr, uid, fields, context)
	picking_obj = self.pool.get('stock.picking')
        picking_ids = context.get('active_ids', [])
        picking = picking_obj.browse(cr, uid, picking_ids)[0]
	res.update({'weight': 1.0, 'recipient_address': picking.company_id.partner_id.id})
	if picking.carrier_id and picking.carrier_id.service:
	    res.update({
			'delivery_method': picking.carrier_id.id,
			'carrier': picking.carrier_id.service.carrier,
	    })


	if picking.partner_id.country_id.code != 'US' or \
		picking.partner_id.city.lower() in ['apo', 'fpo', 'dpo']:

	    res['customs_tab'] = True

        return res


    def onchange_delivery_method(self, cr, uid, ids, delivery_method):
	delivery_obj = self.pool.get('delivery.carrier')
	carrier = delivery_obj.browse(cr, uid, delivery_method)
	return {'value': {'carrier': carrier.service.carrier}}	


    def onchange_shape_dimensions(self, cr, uid, ids, shape_id):
	dimension_obj = self.pool.get('delivery.box.shape')
	length = 0
	width = 0
	height = 0
	if shape_id:
	    dims = dimension_obj.browse(cr, uid, shape_id)
	    length = dims.length
	    width = dims.width
	    height = dims.height

	return {'value': {'length': length, 'width': width, 'height': height}}


    def wizard_prepare_shipment_request(self, cr, uid, ids, context=None):
        wizard = self.browse(cr, uid, ids[0])
	picking_obj = self.pool.get('stock.picking')
	package_obj = self.pool.get('stock.out.package')
	pickings = context.get('active_ids')

	for picking in picking_obj.browse(cr, uid, pickings):
	    vals = {
		'picking': picking.id,
		'weight': wizard.weight or 0,
		'length': wizard.length or 0,
		'width': wizard.width or 0,
		'height': wizard.height or 0,
		'declared_value': wizard.declared_value,
	    }
	    if wizard.return_label:
		vals.update({
			'alternate_sender_address': wizard.alternate_sender_address.id \
				if wizard.alternate_sender_address else picking.partner_id.id,
		})

	    package_id = package_obj.create(cr, uid, vals)
	    package = package_obj.browse(cr, uid, package_id)

	    picking.carrier_id = wizard.delivery_method.id

	    self.generate_shipping_label(cr, uid, wizard.delivery_method.service.carrier, package)

	return True


    def generate_shipping_label(self, cr, uid, carrier, package):
        if carrier == 'ups':
	    self.generate_ups_label(cr, uid, package)

	else:
	    self.generate_endicia_label(cr, uid, package)
	    

        datas = {'ids' : [package.id]}
        datas['form'] = {}
        return {
            'type': 'ir.actions.report.xml',
            'report_name':'omniship.label',
            'datas' : datas,
       }
