import React from 'react';

const Header = () => {
  return (
    <header className="bg-nba-blue shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="flex items-center">
                <div className="w-8 h-8 bg-nba-orange rounded-full flex items-center justify-center mr-3">
                  <span className="text-white font-bold text-lg">🏀</span>
                </div>
                <h1 className="text-xl font-bold text-white">NBA Fantasy Dashboard</h1>
              </div>
            </div>
          </div>
          
          <div className="hidden md:block">
            <div className="ml-10 flex items-baseline space-x-4">
              <span className="text-gray-300 text-sm">
                Player Statistics & Draft Management
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
