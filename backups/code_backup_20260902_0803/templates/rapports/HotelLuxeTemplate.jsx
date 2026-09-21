import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const LuxuryHotelTemplate = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [selectedRoom, setSelectedRoom] = useState(null)

  // Animation variants pour le header
  const headerVariants = {
    hidden: { opacity: 0, y: -20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.8, ease: 'easeOut' }
    }
  }

  // Animation pour le hero title
  const titleVariants = {
    hidden: { opacity: 0, y: 50 },
    visible: (i) => ({
      opacity: 1,
      y: 0,
      transition: {
        delay: i * 0.15,
        duration: 0.9,
        ease: 'easeOut'
      }
    })
  }

  // Stagger animation pour les cards
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2
      }
    }
  }

  const cardVariants = {
    hidden: { opacity: 0, y: 30, scale: 0.95 },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: {
        type: 'spring',
        stiffness: 300,
        damping: 25
      }
    },
    hover: {
      y: -8,
      scale: 1.02,
      transition: {
        type: 'spring',
        stiffness: 400,
        damping: 25
      }
    }
  }

  // Parallax scroll effect
  const scrollVariants = {
    hidden: { opacity: 0, y: 100 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: 'spring',
        stiffness: 100,
        damping: 30
      }
    }
  }

  const rooms = [
    {
      id: 1,
      name: 'Suite Panoramique',
      category: 'Ultra Luxury',
      image: 'https://images.unsplash.com/photo-1631049307038-da0ec9d70304?auto=format&fit=crop&w=800&q=80',
      price: '520€',
      features: ['Vue mer privée', 'Spa en chambre', 'Butler 24/7'],
      rating: 9.8
    },
    {
      id: 2,
      name: 'Chambre Prestige',
      category: 'Premium',
      image: 'https://images.unsplash.com/photo-1611892473320-b5b6ec8b102d?auto=format&fit=crop&w=800&q=80',
      price: '380€',
      features: ['Terrasse vue', 'Minibar premium', 'Wellness'],
      rating: 9.6
    },
    {
      id: 3,
      name: 'Suite Déluxe',
      category: 'Luxury',
      image: 'https://images.unsplash.com/photo-1512918386052-80404dc91905?auto=format&fit=crop&w=800&q=80',
      price: '280€',
      features: ['Mobilier design', 'Baignoire îlot', 'Hammam'],
      rating: 9.4
    }
  ]

  const services = [
    { icon: '🌟', title: 'Concierge Premium', desc: 'Accès à tous les privilèges VIP' },
    { icon: '🍽️', title: 'Gastronomie', desc: 'Restaurant 3 Michelin et Wine Bar' },
    { icon: '🏊', title: 'Wellness', desc: 'Spa signature et piscine intérieure' },
    { icon: '🎭', title: 'Events', desc: 'Salles pour galas et réceptions' }
  ]

  return (
    <div className="min-h-screen bg-black text-white overflow-hidden">
      {/* HEADER */}
      <motion.header
        variants={headerVariants}
        initial="hidden"
        animate="visible"
        className="fixed top-0 left-0 right-0 z-50 px-6 py-4 bg-black/40 backdrop-blur-md border-b border-white/5"
      >
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <motion.div
            whileHover={{ scale: 1.05 }}
            className="text-2xl font-light tracking-widest"
          >
            AURELIA
          </motion.div>
          <nav className="hidden md:flex gap-8">
            {['Suites', 'Services', 'Expériences', 'Contact'].map((item) => (
              <motion.a
                key={item}
                whileHover={{ color: '#d4a574', x: 4 }}
                className="text-sm font-light tracking-wide cursor-pointer text-white/70 hover:text-white transition-colors"
              >
                {item}
              </motion.a>
            ))}
          </nav>
          <motion.button
            whileHover={{ scale: 1.05 }}
            className="px-6 py-2 bg-yellow-600/80 hover:bg-yellow-500 rounded text-white font-medium transition-colors"
          >
            Réserver
          </motion.button>
        </div>
      </motion.header>

      {/* HERO SECTION */}
      <section className="relative h-screen overflow-hidden">
        {/* Vidéo background avec overlay */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 2 }}
          className="absolute inset-0"
        >
          <div
            className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black"
            style={{
              backgroundImage: 'url(https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1920&q=80)',
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              backgroundAttachment: 'fixed'
            }}
          />
          {/* Animated gradient overlay */}
          <motion.div
            animate={{
              background: [
                'radial-gradient(circle at 0% 0%, rgba(212,165,116,0.1), transparent)',
                'radial-gradient(circle at 100% 100%, rgba(212,165,116,0.1), transparent)',
                'radial-gradient(circle at 0% 0%, rgba(212,165,116,0.1), transparent)'
              ]
            }}
            transition={{ duration: 8, repeat: Infinity }}
            className="absolute inset-0"
          />
        </motion.div>

        {/* Content */}
        <div className="relative h-full flex flex-col justify-center items-center text-center px-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3, duration: 1 }}
            className="mb-6"
          >
            <span className="inline-block text-sm font-light tracking-widest text-yellow-400 mb-4">
              BIENVENUE À AURELIA
            </span>
          </motion.div>

          {/* Main title avec split animation */}
          <div className="overflow-hidden mb-6">
            <motion.h1
              custom={0}
              variants={titleVariants}
              initial="hidden"
              animate="visible"
              className="text-6xl md:text-8xl font-light tracking-tight"
            >
              Luxe
            </motion.h1>
          </div>
          <div className="overflow-hidden mb-8">
            <motion.h1
              custom={1}
              variants={titleVariants}
              initial="hidden"
              animate="visible"
              className="text-6xl md:text-8xl font-light tracking-tight text-yellow-400"
            >
              Intemporel
            </motion.h1>
          </div>

          <motion.p
            custom={2}
            variants={titleVariants}
            initial="hidden"
            animate="visible"
            className="max-w-2xl text-xl text-white/70 font-light mb-12"
          >
            Une symphonie d'élégance et de confort où chaque détail respire la sophistication
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8, duration: 0.8 }}
            className="flex gap-6"
          >
            <motion.button
              whileHover={{ scale: 1.05, backgroundColor: '#d4a574' }}
              whileTap={{ scale: 0.95 }}
              className="px-10 py-3 bg-yellow-600 text-black font-medium rounded transition-colors"
            >
              Découvrir les Suites
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.05, borderColor: '#d4a574' }}
              whileTap={{ scale: 0.95 }}
              className="px-10 py-3 border border-white/30 rounded hover:border-yellow-500 transition-colors"
            >
              Regarder la vidéo
            </motion.button>
          </motion.div>

          {/* Scroll indicator */}
          <motion.div
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute bottom-10"
          >
            <svg
              className="w-6 h-6 text-white/50"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 14l-7 7m0 0l-7-7m7 7V3"
              />
            </svg>
          </motion.div>
        </div>
      </section>

      {/* SUITES SECTION */}
      <section className="py-24 px-6 bg-black">
        <div className="max-w-7xl mx-auto">
          <motion.div
            variants={scrollVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-100px' }}
            className="text-center mb-16"
          >
            <h2 className="text-5xl font-light mb-4 tracking-tight">Nos Collections</h2>
            <p className="text-white/60 max-w-2xl mx-auto text-lg">
              Chaque suite est une composition de luxe et d'intimité, conçue pour transcender vos attentes
            </p>
          </motion.div>

          {/* Rooms Grid */}
          <motion.div
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-100px' }}
            className="grid md:grid-cols-3 gap-8"
          >
            {rooms.map((room) => (
              <motion.div
                key={room.id}
                variants={cardVariants}
                whileHover="hover"
                onClick={() => setSelectedRoom(room)}
                className="group cursor-pointer"
              >
                {/* Image container */}
                <div className="relative overflow-hidden rounded-lg h-64 mb-6">
                  <motion.img
                    whileHover={{ scale: 1.08 }}
                    transition={{ duration: 0.6 }}
                    src={room.image}
                    alt={room.name}
                    className="w-full h-full object-cover"
                  />
                  <motion.div
                    initial={{ opacity: 0 }}
                    whileHover={{ opacity: 1 }}
                    className="absolute inset-0 bg-black/40 flex items-end p-6"
                  >
                    <span className="text-yellow-400 text-sm font-medium">{room.category}</span>
                  </motion.div>
                </div>

                {/* Content */}
                <div>
                  <h3 className="text-2xl font-light mb-2">{room.name}</h3>
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-yellow-400 text-xl font-medium">{room.price}/nuit</span>
                    <motion.span
                      whileHover={{ scale: 1.1 }}
                      className="text-white/70"
                    >
                      ⭐ {room.rating}
                    </motion.span>
                  </div>

                  {/* Features */}
                  <div className="space-y-2 mb-4">
                    {room.features.map((feature, idx) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, x: -20 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.1 }}
                        viewport={{ once: true }}
                        className="text-white/60 text-sm flex items-center gap-2"
                      >
                        <span>✓</span> {feature}
                      </motion.div>
                    ))}
                  </div>

                  <motion.button
                    whileHover={{ x: 6 }}
                    className="text-yellow-400 font-light text-sm tracking-wide"
                  >
                    En savoir plus →
                  </motion.button>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* SERVICES SECTION */}
      <section className="py-24 px-6 bg-gradient-to-b from-black to-gray-900">
        <div className="max-w-7xl mx-auto">
          <motion.h2
            variants={scrollVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-100px' }}
            className="text-5xl font-light text-center mb-16 tracking-tight"
          >
            Expériences Curated
          </motion.h2>

          <motion.div
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-100px' }}
            className="grid md:grid-cols-4 gap-6"
          >
            {services.map((service, idx) => (
              <motion.div
                key={idx}
                variants={cardVariants}
                whileHover="hover"
                className="p-8 rounded-lg border border-white/10 hover:border-yellow-400/50 transition-colors bg-white/5 backdrop-blur"
              >
                <div className="text-5xl mb-4">{service.icon}</div>
                <h3 className="text-xl font-light mb-2">{service.title}</h3>
                <p className="text-white/60 text-sm leading-relaxed">{service.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* CTA Final */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1 }}
        className="py-24 px-6 bg-gradient-to-r from-yellow-900/20 to-yellow-600/10 border-t border-yellow-600/30"
      >
        <div className="max-w-4xl mx-auto text-center">
          <motion.h2
            initial={{ y: 30, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.2 }}
            viewport={{ once: true }}
            className="text-5xl font-light mb-6"
          >
            Prêt pour l'Extraordinaire ?
          </motion.h2>
          <motion.p
            initial={{ y: 30, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4 }}
            viewport={{ once: true }}
            className="text-white/70 mb-8 text-lg"
          >
            Réservez votre séjour et plongez dans l'univers de Aurelia
          </motion.p>
          <motion.button
            whileHover={{ scale: 1.1, backgroundColor: '#d4a574' }}
            whileTap={{ scale: 0.95 }}
            className="px-12 py-4 bg-yellow-600 text-black font-medium rounded transition-all text-lg"
          >
            Réserver Maintenant
          </motion.button>
        </div>
      </motion.section>

      {/* Modal pour détails suite */}
      <AnimatePresence>
        {selectedRoom && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSelectedRoom(null)}
            className="fixed inset-0 bg-black/80 backdrop-blur z-40 flex items-center justify-center p-4"
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-gray-900 rounded-lg max-w-2xl w-full p-8 border border-white/10"
            >
              <motion.img
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                src={selectedRoom.image}
                alt={selectedRoom.name}
                className="w-full h-80 object-cover rounded-lg mb-6"
              />
              <h2 className="text-4xl font-light mb-4">{selectedRoom.name}</h2>
              <p className="text-yellow-400 mb-6">{selectedRoom.category}</p>
              <div className="grid grid-cols-2 gap-4 mb-8">
                {selectedRoom.features.map((feature, idx) => (
                  <div key={idx} className="text-white/70">
                    ✓ {feature}
                  </div>
                ))}
              </div>
              <button
                onClick={() => setSelectedRoom(null)}
                className="w-full py-3 bg-yellow-600 text-black font-medium rounded mb-4"
              >
                Réserver - {selectedRoom.price}/nuit
              </button>
              <button
                onClick={() => setSelectedRoom(null)}
                className="w-full py-3 border border-white/20 rounded text-white/70 hover:text-white transition-colors"
              >
                Fermer
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default LuxuryHotelTemplate
